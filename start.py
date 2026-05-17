from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repository import UserRepo
from bot.keyboards.inline import main_menu_kb

router = Router()

WELCOME = (
    "👋 <b>Добро пожаловать!</b>\n\n"
    "Мы пишем студенческие работы под заказ:\n"
    "• Эссе — 300 ₽\n"
    "• Реферат — 400 ₽\n"
    "• Курсовая — 550 ₽ (включает 1 бесплатную правку)\n\n"
    "Выберите действие:"
)


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    await UserRepo(session).get_or_create(
        message.from_user.id, message.from_user.username, message.from_user.full_name
    )
    await message.answer(WELCOME, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == "back:main")
async def back_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(WELCOME, reply_markup=main_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(lambda c: c.data == "support")
async def support_info(callback: CallbackQuery):
    await callback.answer(
        "По всем вопросам пишите: @ваш_username_поддержки",
        show_alert=True,
    )
