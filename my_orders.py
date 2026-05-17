from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import OrderStatus
from bot.database.repository import OrderRepo
from bot.keyboards.inline import order_detail_kb, main_menu_kb

router = Router()

STATUS_TEXT = {
    OrderStatus.NEW:       "⏳ Ожидает оплаты",
    OrderStatus.PAID:      "📋 В очереди",
    OrderStatus.IN_WORK:   "🔧 В работе",
    OrderStatus.DONE:      "✅ Готов",
    OrderStatus.REVISION:  "✏️ На правках",
    OrderStatus.CANCELLED: "❌ Отменён",
}

WORK_LABELS = {"essay": "Эссе", "referat": "Реферат", "kursovaya": "Курсовая"}


@router.callback_query(F.data == "my_orders")
async def my_orders(callback: CallbackQuery, session: AsyncSession):
    orders = await OrderRepo(session).get_user_orders(callback.from_user.id)
    if not orders:
        await callback.answer("У вас пока нет заказов.", show_alert=True)
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()

    lines = ["📋 <b>Ваши заказы:</b>\n"]
    for o in orders[:10]:
        status = STATUS_TEXT.get(o.status, "•")
        label  = WORK_LABELS.get(o.work_type.value, "—")
        star   = "⭐ " if o.is_priority else ""
        lines.append(f"{star}<b>#{o.id}</b> {label} — {status}")
        builder.row(InlineKeyboardButton(
            text=f"#{o.id} {label[:20]}",
            callback_data=f"order_detail:{o.id}",
        ))

    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back:main"))
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("order_detail:"))
async def order_detail(callback: CallbackQuery, session: AsyncSession):
    order_id = int(callback.data.split(":")[1])
    order = await OrderRepo(session).get(order_id)

    if not order or order.user_id != callback.from_user.id:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    label  = WORK_LABELS.get(order.work_type.value, "—")
    status = STATUS_TEXT.get(order.status, "—")
    star   = "⭐ Приоритет\n" if order.is_priority else ""

    text = (
        f"📄 <b>Заказ #{order.id}</b>\n"
        f"{star}"
        f"Тип: {label}\n"
        f"Тема: {order.topic}\n"
        f"Комментарий: {order.comment or '—'}\n"
        f"Статус: {status}\n"
        f"Правок сделано: {order.revision_count}\n"
        f"Бесплатных правок осталось: {order.free_revisions_left}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=order_detail_kb(
            order.id, order.work_type.value, order.free_revisions_left, order.status.value
        ),
        parse_mode="HTML",
    )
    await callback.answer()
