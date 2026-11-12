import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, GEMINI_API_KEYS, GROQ_API_KEYS
from database.db import init_db
from database.queries import seed_env_keys
from handlers import common, add_words, units, quiz, typing, listening, flashcards, starter_packs, context_quiz, stats, admin, auto_reminder
from handlers.auto_reminder import auto_word_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Bot ishga tushirilmoqda...")
    
    if not BOT_TOKEN:
        logger.error("Xatolik: .env faylida BOT_TOKEN ko'rsatilmagan!")
        return

    # Initialize SQLite database and seed .env keys
    await init_db()
    await seed_env_keys(GEMINI_API_KEYS, GROQ_API_KEYS)
    logger.info("Ma'lumotlar bazasi (SQLite) va API kalitlar tayyor.")

    # Create Bot and Dispatcher
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Include routers
    dp.include_router(admin.router)
    dp.include_router(common.router)
    dp.include_router(add_words.router)
    dp.include_router(units.router)
    dp.include_router(quiz.router)
    dp.include_router(typing.router)
    dp.include_router(listening.router)
    dp.include_router(flashcards.router)
    dp.include_router(context_quiz.router)
    dp.include_router(starter_packs.router)
    dp.include_router(stats.router)
    dp.include_router(auto_reminder.router)

    # Start background 15-min vocabulary scheduler
    scheduler_task = asyncio.create_task(auto_word_scheduler(bot))

    logger.info("Bot muvaffaqiyatli ishga tushdi va xabarlarni kutmoqda...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        scheduler_task.cancel()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
