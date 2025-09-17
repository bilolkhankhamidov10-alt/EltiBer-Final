from __future__ import annotations

import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")

DRIVERS_CHAT_ID = -1002978372872
RATINGS_CHAT_ID = -4861064259
PAYMENTS_CHAT_ID = -4925556700

ADMIN_IDS = [6948926876]

CARD_NUMBER = "5614682216212664"
CARD_HOLDER = "BILOL HAMIDOV"
SUBSCRIPTION_PRICE = 99_000
CARD_NUMBER_DISPLAY = CARD_NUMBER

FREE_TRIAL_ENABLED = True
FREE_TRIAL_DAYS = 30
FREE_TRIAL_DURATION = timedelta(days=FREE_TRIAL_DAYS)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
DATA_DIR = os.path.join(BASE_DIR, "data")

CONTACT_IMAGE_PATH = os.path.join(ASSETS_DIR, "EltiBer.png")
ESLATMA_IMAGE_PATH = os.path.join(ASSETS_DIR, "ESLATMA.png")
CONTACT_IMAGE_URL = ""

CONTACT_PHONE = "+998 50 330 77 07"
CONTACT_PHONE_LINK = CONTACT_PHONE.replace(" ", "")
CONTACT_TG = "EltiBer_admin"

DRIVER_BTN = "👨‍✈️ Haydovchi bo'lish"
CONTACT_BTN = "📞 Biz bilan bog'lanish"

CANCEL = "❌ Bekor qilish"
BACK = "◀️ Ortga"
HOZIR = "🕒 Hozir"
BOSHQA = "⌨️ Boshqa vaqt"

__all__ = [
    "TOKEN",
    "DRIVERS_CHAT_ID",
    "RATINGS_CHAT_ID",
    "PAYMENTS_CHAT_ID",
    "ADMIN_IDS",
    "CARD_NUMBER",
    "CARD_HOLDER",
    "SUBSCRIPTION_PRICE",
    "CARD_NUMBER_DISPLAY",
    "FREE_TRIAL_ENABLED",
    "FREE_TRIAL_DAYS",
    "FREE_TRIAL_DURATION",
    "BASE_DIR",
    "ASSETS_DIR",
    "DATA_DIR",
    "CONTACT_IMAGE_PATH",
    "ESLATMA_IMAGE_PATH",
    "CONTACT_IMAGE_URL",
    "CONTACT_PHONE",
    "CONTACT_PHONE_LINK",
    "CONTACT_TG",
    "DRIVER_BTN",
    "CONTACT_BTN",
    "CANCEL",
    "BACK",
    "HOZIR",
    "BOSHQA",
]
