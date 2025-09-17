import asyncio

from app import bot, dp  # noqa: F401
import app.handlers  # noqa: F401,E402,F401
from app.trial import start_trial_watcher


async def main() -> None:
    print("Bot ishga tushmoqda...")
    await bot.delete_webhook(drop_pending_updates=True)
    start_trial_watcher()
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
