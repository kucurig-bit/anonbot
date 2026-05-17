"""
Управление очередью заказов в admin-группе.
Одно сообщение обновляется при каждом изменении.
"""
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import OrderStatus
from bot.database.repository import OrderRepo

STATUS_EMOJI = {
    OrderStatus.PAID:     "⏳",
    OrderStatus.IN_WORK:  "🔧",
    OrderStatus.REVISION: "✏️",
    OrderStatus.DONE:     "✅",
}

WORK_LABELS = {
    "essay":     "Эссе",
    "referat":   "Реферат",
    "kursovaya": "Курсовая",
}

# ID «доски очереди» — храним в памяти (достаточно для одного процесса)
_queue_board_message_id: int | None = None


def _render(orders) -> str:
    if not orders:
        return "📋 <b>Очередь пуста</b>"

    lines = ["📋 <b>Очередь заказов</b>\n"]
    for i, o in enumerate(orders, 1):
        emoji  = STATUS_EMOJI.get(o.status, "•")
        star   = "⭐" if o.is_priority else "  "
        label  = WORK_LABELS.get(o.work_type.value, o.work_type.value)
        topic  = o.topic[:50] + ("…" if len(o.topic) > 50 else "")
        rev    = f" | правок: {o.revision_count}" if o.revision_count else ""
        lines.append(f"{star}{i}. {emoji} <b>#{o.id}</b> {label} — {topic}{rev}")

    lines.append("\nНажмите на номер заказа для действий: /order_<номер>")
    return "\n".join(lines)


async def refresh_queue(bot: Bot, session: AsyncSession) -> None:
    """Обновляет или создаёт сообщение-доску очереди в admin-группе."""
    global _queue_board_message_id

    if not settings.admin_group_id:
        return

    repo   = OrderRepo(session)
    orders = await repo.get_queue()
    text   = _render(orders)

    try:
        if _queue_board_message_id:
            await bot.edit_message_text(
                text=text,
                chat_id=settings.admin_group_id,
                message_id=_queue_board_message_id,
                parse_mode="HTML",
            )
        else:
            msg = await bot.send_message(
                chat_id=settings.admin_group_id,
                text=text,
                parse_mode="HTML",
            )
            _queue_board_message_id = msg.message_id
    except Exception:
        # Если сообщение удалили — создаём новое
        msg = await bot.send_message(
            chat_id=settings.admin_group_id,
            text=text,
            parse_mode="HTML",
        )
        _queue_board_message_id = msg.message_id
