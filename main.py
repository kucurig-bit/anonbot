import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.database.session import create_tables
from bot.middlewares.db import DbSessionMiddleware
from bot.handlers import start, order, revision, my_orders, admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


async def main():
    logging.info("Создание таблиц БД...")
    await create_tables()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())

    # admin — первым, чтобы фильтр IsAdmin срабатывал раньше общих хендлеров
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(order.router)
    dp.include_router(revision.router)
    dp.include_router(my_orders.router)

    logging.info("Бот запущен.")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
