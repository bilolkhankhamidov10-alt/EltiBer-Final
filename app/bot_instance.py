from aiogram import Bot, Dispatcher

from .config import TOKEN

bot = Bot(token=TOKEN)
dp = Dispatcher()

__all__ = ["bot", "dp"]
