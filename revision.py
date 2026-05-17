"""
Флоу правок для курсовой работы.
- Бесплатная (если free_revisions_left > 0): сразу принимается
- Платная: пользователь выбирает способ оплаты → после оплаты правка принимается
Пользователь может отправить текст И/ИЛИ файл.
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import PaymentType, PaymentStatus, OrderStatus
from bot.database.repository import OrderRepo, RevisionRepo, PaymentRepo
from bot.keyboards.inline import pay_method_kb, check_payment_kb, revision_kb
from bot.services.payment import create_yukassa_payment, check_yukassa_payment, send_stars_invoice
from bot.utils.states import RevisionForm
from bot.utils.queue import refresh_queue

router = Router()


# ── Инициализация правки ──────────────────────────────────

@router.callback_query(F.data.startswith("revision:init:"))
async def revision_init(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    order_id = int(callback.data.split(":")[2])
    order = await OrderRepo(session).get(order_id)

    if not order or order.user_id != callback.from_user.id:
        await callback.answer("Заказ не найден.", show_alert=True)
        return
    if order.work_type.value != "kursovaya":
        await callback.answer("Правки доступны только для курсовых работ.", show_alert=True)
        return

    free_left = order.free_revisions_left
    cost = 0 if free_left > 0 else settings.price_revision

    await state.set_state(RevisionForm.entering)
    await state.update_data(order_id=order_id, free_left=free_left, cost=cost)

    cost_text = "бесплатно" if cost == 0 else f"+{cost} ₽"
    await callback.message.answer(
        f"✏️ <b>Правки по заказу #{order_id}</b>\n\n"
        f"Эта правка: <b>{cost_text}</b>\n"
        f"Бесплатных осталось после: {max(0, free_left - 1)}\n\n"
        "Напишите текст правок и/или прикрепите файл с пометками.\n"
        "<i>Отправьте сообщение (можно несколько) — затем напишите /done</i>",
        parse_mode="HTML",
    )
    await callback.answer()


# ── Сбор сообщений пользователя (текст + файл) ───────────

@router.message(RevisionForm.entering, F.text | F.document)
async def revision_collect(message: Message, state: FSMContext):
    data = await state.get_data()

    # Накапливаем текст
    texts = data.get("rev_texts", [])
    file_ids = data.get("rev_files", [])

    if message.text and message.text != "/done":
        texts.append(message.text)
    if message.document:
        file_ids.append(message.document.file_id)
        if message.caption:
            texts.append(message.caption)

    await state.update_data(rev_texts=texts, rev_files=file_ids)

    if message.text == "/done" or (not message.document and message.text == "/done"):
        await _submit_revision(message, state)
        return

    await message.answer("📎 Принято. Продолжайте или напишите /done для отправки.")


@router.message(RevisionForm.entering, F.text == "/done")
async def revision_done_cmd(message: Message, state: FSMContext):
    await _submit_revision(message, state)


async def _submit_revision(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data["order_id"]
    cost = data["cost"]
    free_left = data["free_left"]
    texts = data.get("rev_texts", [])
    files = data.get("rev_files", [])

    if not texts and not files:
        await message.answer("⚠️ Вы ничего не отправили. Напишите текст или прикрепите файл.")
        return

    # Объединяем текст
    combined_text = "\n---\n".join(texts) if texts else None
    file_id = files[0] if files else None   # берём первый файл (расширить можно)

    await state.update_data(combined_text=combined_text, file_id=file_id)

    if free_left > 0:
        # Бесплатная — сразу отправляем
        await state.set_state(None)
        await _finalize_revision(message, state, is_paid=False)
    else:
        # Платная — оплата
        await state.set_state(RevisionForm.paying)
        await message.answer(
            f"💰 Правка платная: <b>{cost} ₽</b>\nВыберите способ оплаты:",
            reply_markup=pay_method_kb(order_id, cost, "revision"),
            parse_mode="HTML",
        )


# ── Оплата правки — ЮКасса ───────────────────────────────

@router.callback_query(RevisionForm.paying, F.data.startswith("pay:yukassa:"))
async def revision_pay_yukassa(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    order_id = data["order_id"]
    cost = data["cost"]

    try:
        ext_id, url = await create_yukassa_payment(
            amount=cost,
            description=f"Правка по заказу #{order_id}",
            order_id=order_id,
        )
        pay_repo = PaymentRepo(session)
        payment = await pay_repo.create(
            user_id=callback.from_user.id,
            order_id=order_id,
            payment_type=PaymentType.REVISION,
            amount=cost,
        )
        await pay_repo.set_external(payment.id, ext_id)
        await state.update_data(rev_payment_id=payment.id)

        await callback.message.edit_text(
            f"💳 <a href='{url}'>Оплатить правку {cost} ₽</a>\n\n"
            "После оплаты нажмите кнопку ниже:",
            reply_markup=check_payment_kb(order_id, "revision"),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
    await callback.answer()


@router.callback_query(F.data.startswith("check_pay:") and F.data.endswith(":revision"))
async def revision_check_pay(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    parts = callback.data.split(":")
    order_id = int(parts[1])
    data = await state.get_data()
    pay_id = data.get("rev_payment_id")

    if not pay_id:
        await callback.answer("Платёж не найден.", show_alert=True)
        return

    pay_repo = PaymentRepo(session)
    from bot.database.repository import PaymentRepo as PR
    result = await PR(session).get_pending_by_order(order_id, PaymentType.REVISION)
    if not result:
        await callback.answer("Платёж не найден.", show_alert=True)
        return

    paid = await check_yukassa_payment(result.external_id)
    if paid:
        await pay_repo.set_status(result.id, PaymentStatus.SUCCEEDED)
        await _finalize_revision(callback.message, state, is_paid=True, session=session, bot=bot)
        await state.clear()
    else:
        await callback.answer("Оплата ещё не поступила.", show_alert=True)


# ── Финализация правки ────────────────────────────────────

async def _finalize_revision(target, state: FSMContext, is_paid: bool, session=None, bot=None):
    data = await state.get_data()
    order_id = data["order_id"]
    text = data.get("combined_text")
    file_id = data.get("file_id")

    # Нужна сессия и бот — если не переданы, берём из контекста (для бесплатных правок)
    if session is None:
        # Используется только из _submit_revision где session нет — получим через DI в хендлере
        return

    rev_repo = RevisionRepo(session)
    await rev_repo.create(
        order_id=order_id,
        is_paid=is_paid,
        comment=text,
        file_id=file_id,
    )

    order_repo = OrderRepo(session)
    await order_repo.decrement_free_revision(order_id)

    # Уведомляем админа
    if bot and settings.admin_group_id:
        msg = f"✏️ <b>Правки по заказу #{order_id}</b>\n"
        msg += "💰 Платная\n" if is_paid else "🆓 Бесплатная\n"
        if text:
            msg += f"\n<b>Текст правок:</b>\n{text[:1000]}"
        await bot.send_message(settings.admin_group_id, msg, parse_mode="HTML")
        if file_id:
            await bot.send_document(
                settings.admin_group_id,
                file_id,
                caption=f"Файл с правками к заказу #{order_id}",
            )

    await refresh_queue(bot, session)

    done_text = "✅ Правки отправлены! Ожидайте обновлённую версию работы."
    try:
        await target.edit_text(done_text)
    except Exception:
        await target.answer(done_text)


# Хэндлер для бесплатных правок с доступом к session и bot
@router.message(RevisionForm.entering, F.text == "/done")
async def revision_free_finalize(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    data = await state.get_data()
    if data.get("cost", 1) == 0:
        await _finalize_revision(message, state, is_paid=False, session=session, bot=bot)
        await state.clear()
