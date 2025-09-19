from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile
)
# CopyTextButton yangi Telegram Bot API’da bor. Aiogram versiyangizda bo‘lmasa, fallback ishlaydi.
try:
    from aiogram.types import CopyTextButton
    SUPPORTS_COPY_TEXT = True
except Exception:
    SUPPORTS_COPY_TEXT = False

from aiogram.filters import Command, CommandStart
import asyncio
from datetime import datetime, timedelta, time as dtime
import os
import json
from typing import Any
import csv
from dotenv import load_dotenv

# ================== SOZLAMALAR ==================
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")
RATINGS_CHAT_ID  = -4861064259         # 📊 Baholar log guruhi
PAYMENTS_CHAT_ID = -4925556700         # 💳 Cheklar guruhi

ADMIN_IDS = [6948926876]

CARD_NUMBER = "5614682216212664"
CARD_HOLDER = "BILOL HAMIDOV"
SUBSCRIPTION_PRICE = 99_000
CARD_NUMBER_DISPLAY = CARD_NUMBER

MAX_DRIVER_REGIONS = 7
REGION_PRICING = {
    1: 99_000,
    2: 179_000,
    3: 259_000,
    4: 339_000,
    5: 419_000,
}
MAX_REGION_PRICING = 499_000

bot = Bot(token=TOKEN)
dp  = Dispatcher()

# ---- Assets papka (rasmlar loyiha ichida) ----
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

CONTACT_IMAGE_PATH = os.path.join(ASSETS_DIR, "EltiBer.png")
ESLATMA_IMAGE_PATH = os.path.join(ASSETS_DIR, "ESLATMA.png")
CONTACT_IMAGE_URL  = ""   # xohlasa zahira URL

# ======= PERSISTENCE (user_profiles -> JSON) =======
DATA_DIR = os.path.join(BASE_DIR, "data")
USERS_JSON = os.path.join(DATA_DIR, "users.json")
REGIONS_JSON = os.path.join(DATA_DIR, "regions.json")
STORE_LOCK = asyncio.Lock()

def _ensure_data_dir():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception:
        pass

def _load_json(path: str, default: Any):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

async def _save_json(path: str, data: Any):
    _ensure_data_dir()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


def _ensure_regions_template() -> None:
    if os.path.exists(REGIONS_JSON):
        return
    _ensure_data_dir()
    sample = [
        {
            "name": f"Hudud {idx}",
            "order_chat_id": 0,
            "driver_chat_id": 0,
        }
        for idx in range(1, 19)
    ]
    try:
        with open(REGIONS_JSON, "w", encoding="utf-8") as f:
            json.dump(sample, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_regions_config() -> dict[str, dict[str, int]]:
    data = _load_json(REGIONS_JSON, None)
    if not data:
        _ensure_regions_template()
        raise RuntimeError(
            f"regions.json fayli topilmadi yoki bo'sh. Iltimos, {REGIONS_JSON} ichida hudud nomlari va guruh IDlarini kiriting."
        )

    regions: dict[str, dict[str, int]] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = (entry.get("name") or "").strip()
        if not name:
            continue

        def _as_int(value, fallback):
            try:
                return int(value)
            except Exception:
                return fallback

        order_chat = _as_int(entry.get("order_chat_id"), 0)
        driver_chat = _as_int(entry.get("driver_chat_id"), 0)
        if order_chat == 0:
            raise RuntimeError(
                f"regions.json: '{name}' uchun order_chat_id to'ldirilmagan. {REGIONS_JSON} faylini yangilang."
            )
        if driver_chat == 0:
            driver_chat = order_chat

        regions[name] = {
            "order_chat_id": order_chat,
            "driver_chat_id": driver_chat,
        }

    if not regions:
        raise RuntimeError(
            "regions.json bo'sh. Iltimos, hech bo'lmaganda bitta hududni sozlang."
        )
    return regions


REGIONS = _load_regions_config()
REGION_NAMES = list(REGIONS.keys())
ORDER_CHAT_IDS = {name: cfg["order_chat_id"] for name, cfg in REGIONS.items()}
DRIVER_CHAT_IDS = {
    name: (cfg.get("driver_chat_id") or cfg["order_chat_id"])
    for name, cfg in REGIONS.items()
}
DRIVER_CHAT_ID_SET = set(DRIVER_CHAT_IDS.values())
DRIVER_CHAT_ID_TO_REGION = {chat_id: name for name, chat_id in DRIVER_CHAT_IDS.items()}


def resolve_region_name(value: str | None) -> str | None:
    if not value:
        return None
    needle = value.strip().lower()
    for name in REGION_NAMES:
        if needle == name.lower():
            return name
    return None


def normalize_region_list(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    if not values:
        return result
    if isinstance(values, str):
        values = [values]
    for item in values:
        name = resolve_region_name(str(item))
        if name and name not in seen:
            seen.add(name)
            result.append(name)
        if len(result) >= MAX_DRIVER_REGIONS:
            break
    return result


def get_profile_regions(uid: int) -> list[str]:
    profile = user_profiles.get(uid, {})
    regions = profile.get("regions")
    if regions:
        return normalize_region_list(regions)
    legacy = profile.get("region")
    if legacy:
        return normalize_region_list([legacy])
    return []


def set_profile_regions(uid: int, regions) -> list[str]:
    normalized = normalize_region_list(regions)
    profile = user_profiles.setdefault(uid, {})
    if normalized:
        profile["regions"] = normalized
        profile["last_region"] = normalized[-1]
    else:
        profile.pop("regions", None)
        profile.pop("last_region", None)
    profile.pop("region", None)
    return normalized


def add_profile_regions(uid: int, regions) -> list[str]:
    current = get_profile_regions(uid)
    for region in normalize_region_list(regions):
        if region not in current and len(current) < MAX_DRIVER_REGIONS:
            current.append(region)
    return set_profile_regions(uid, current)


def _normalize_existing_regions() -> None:
    for uid in list(user_profiles.keys()):
        set_profile_regions(uid, get_profile_regions(uid))

    for uid, data in list(subscriptions.items()):
        regions = data.get("regions") or data.get("region")
        normalized = normalize_region_list(regions)
        data["regions"] = normalized
        if normalized:
            data["last_region"] = normalized[-1]
        else:
            data.pop("last_region", None)
        data.pop("region", None)

    for uid, data in list(trial_members.items()):
        regions = data.get("regions") or data.get("region")
        normalized = normalize_region_list(regions)
        data["regions"] = normalized
        if normalized:
            data["last_region"] = normalized[-1]
        else:
            data.pop("last_region", None)
        data.pop("region", None)

    for uid, info in list(pending_invites.items()):
        if isinstance(info, dict) and "region" in info:
            region = resolve_region_name(info.get("region"))
            if not region:
                pending_invites.pop(uid, None)
                continue
            pending_invites[uid] = {
                region: {
                    "msg_id": info.get("msg_id"),
                    "link": info.get("link"),
                    "chat_id": info.get("chat_id"),
                    "region": region,
                }
            }

def get_order_chat_id(region: str) -> int:
    if region not in ORDER_CHAT_IDS:
        raise RuntimeError(f"Noma'lum hudud: {region}")
    return ORDER_CHAT_IDS[region]


def get_driver_chat_id(region: str) -> int:
    if region not in DRIVER_CHAT_IDS:
        raise RuntimeError(f"Noma'lum hudud: {region}")
    return DRIVER_CHAT_IDS[region]


async def send_region_invite(uid: int, region: str, header_text: str) -> bool:
    chat_id = get_driver_chat_id(region)
    try:
        invite = await bot.create_chat_invite_link(
            chat_id=chat_id,
            name=f"driver-{region}-{uid}-{int(datetime.now().timestamp())}",
            member_limit=1,
        )
        invite_link = invite.invite_link
    except Exception as exc:
        for admin in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin,
                    f"❌ {region} hududi uchun haydovchi silka yaratilmagan (user {uid}): {exc}",
                )
            except Exception:
                pass
        return False

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"👥 {region} haydovchilar guruhiga qo‘shilish",
                    url=invite_link,
                )
            ]
        ]
    )
    try:
        dm = await bot.send_message(
            uid,
            header_text,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        bucket = pending_invites.setdefault(uid, {})
        prev = bucket.get(region)
        if prev and prev.get("msg_id") and prev.get("msg_id") != dm.message_id:
            try:
                await bot.delete_message(chat_id=uid, message_id=prev["msg_id"])
            except Exception:
                pass
        bucket[region] = {
            "msg_id": dm.message_id,
            "link": invite_link,
            "chat_id": chat_id,
            "region": region,
        }
        return True
    except Exception:
        return False


def resolve_driver_regions(driver_id: int) -> list[str]:
    regions: list[str] = []

    def _extend(source) -> None:
        for name in normalize_region_list(source):
            if name not in regions:
                regions.append(name)

    data = driver_onboarding.get(driver_id)
    if data:
        _extend(data.get("regions"))
        _extend(data.get("region"))
        _extend(data.get("last_region"))

    sub = subscriptions.get(driver_id)
    if sub:
        _extend(sub.get("regions"))
        _extend(sub.get("region"))
        _extend(sub.get("last_region"))

    profile = user_profiles.get(driver_id)
    if profile:
        _extend(profile.get("regions"))
        _extend(profile.get("region"))
        _extend(profile.get("last_region"))

    trial = trial_members.get(driver_id)
    if trial:
        _extend(trial.get("regions"))
        _extend(trial.get("region"))
        _extend(trial.get("last_region"))

    pending = pending_invites.get(driver_id)
    if pending:
        if isinstance(pending, dict):
            for key, info in pending.items():
                _extend(key)
                if isinstance(info, dict):
                    _extend(info.get("region"))
        else:
            _extend(pending.get("region"))

    return regions[:MAX_DRIVER_REGIONS]

def load_users_from_disk() -> dict:
    raw = _load_json(USERS_JSON, {})
    fixed = {}
    # JSON kalitlari string bo'lib keladi -> int'ga aylantiramiz
    for k, v in (raw or {}).items():
        try:
            ik = int(k)
        except (ValueError, TypeError):
            ik = k
        fixed[ik] = v
    return fixed

async def save_users_to_disk(users: dict):
    async with STORE_LOCK:
        # Diskka yozishda kalitlarni string ko'rinishida saqlash — normal
        await _save_json(USERS_JSON, {str(k): v for k, v in (users or {}).items()})

# ================== XOTIRA (RAM) ==================
user_profiles = load_users_from_disk()
drafts = {}          # {customer_id: {...}}
driver_onboarding = {}  # {uid: {"stage":..., ...}}
orders = {}             # {customer_id: {...}}
driver_links = {}
pending_invites = {}    # {driver_id: {region: {"msg_id":..., "link":..., "chat_id":...}}}

# ======= FREE TRIAL (30 kun bepul) — QO'SHIMCHA =======
FREE_TRIAL_ENABLED = True
FREE_TRIAL_DAYS = 30
subscriptions = {}   # {driver_id: {"active": True, "regions": [...]}}
trial_members = {}   # {driver_id: {"expires_at": datetime, "regions": [...]}}

_normalize_existing_regions()


def compute_subscription_price(region_count: int) -> int:
    if region_count <= 0:
        return 0
    if region_count <= 5:
        return REGION_PRICING.get(region_count, REGION_PRICING[5])
    return MAX_REGION_PRICING


def format_price(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")

# ================== LABELLAR ==================
CANCEL = "❌ Bekor qilish"
BACK   = "◀️ Ortga"
HOZIR  = "🕒 Hozir"
BOSHQA = "⌨️ Boshqa vaqt"

DRIVER_BTN  = "👨‍✈️ Haydovchi bo'lish"
CONTACT_BTN = "📞 Biz bilan bog'lanish"

REGION_DONE  = "✅ Tanlash tugadi"
REGION_CLEAR = "🗑 Tanlovni tozalash"

CONTACT_PHONE = "+998 50 330 77 07"
CONTACT_PHONE_LINK = CONTACT_PHONE.replace(" ", "")
CONTACT_TG    = "EltiBer_admin"

# ================== KLAVIATURALAR ==================
def rows_from_list(items, per_row=3):
    return [list(map(lambda t: KeyboardButton(text=t), items[i:i+per_row])) for i in range(0, len(items), per_row)]

def keyboard_with_back_cancel(options, per_row=3, show_back=True):
    rows = rows_from_list(options or [], per_row=per_row)
    tail = []
    if show_back: tail.append(KeyboardButton(text=BACK))
    tail.append(KeyboardButton(text=CANCEL))
    rows.append(tail)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def region_keyboard(show_back: bool = False) -> ReplyKeyboardMarkup:
    return keyboard_with_back_cancel(REGION_NAMES, per_row=3, show_back=show_back)


def driver_region_keyboard(include_back: bool) -> ReplyKeyboardMarkup:
    rows = rows_from_list(REGION_NAMES, per_row=3)
    rows.append([KeyboardButton(text=REGION_DONE)])
    rows.append([KeyboardButton(text=REGION_CLEAR)])
    control_row = []
    if include_back:
        control_row.append(KeyboardButton(text=BACK))
    control_row.append(KeyboardButton(text=CANCEL))
    rows.append(control_row)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def vehicle_keyboard():
    VEHICLES = ["🛻 Labo", "🚚 Labodan Kattaroq"]
    return keyboard_with_back_cancel(VEHICLES, per_row=1, show_back=False)

def contact_keyboard(text="📲 Telefon raqamni yuborish"):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text, request_contact=True)]],
        resize_keyboard=True
    )

def share_phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📲 Telefon raqamini ulashish", request_contact=True)],
            [KeyboardButton(text=BACK), KeyboardButton(text=CANCEL)]
        ],
        resize_keyboard=True
    )

def pickup_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True)],
            [KeyboardButton(text=BACK), KeyboardButton(text=CANCEL)]
        ],
        resize_keyboard=True
    )

def order_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚖 Buyurtma berish")],
            [KeyboardButton(text=DRIVER_BTN)],
            [KeyboardButton(text=CONTACT_BTN)],
        ],
        resize_keyboard=True
    )

def when_keyboard():
    return keyboard_with_back_cancel([HOZIR, BOSHQA], per_row=2, show_back=True)

# ================== START ==================
@dp.message(CommandStart())
async def start_command(message: types.Message):
    uid = message.from_user.id
    profile = user_profiles.get(uid)

    if not profile or not profile.get("phone"):
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📞 Telefon raqamingizni yuboring", request_contact=True)]],
            resize_keyboard=True
        )
        await message.answer(
            f"Salom, {message.from_user.full_name}! 👋\n"
            "Iltimos, bir marta telefon raqamingizni yuboring:",
            reply_markup=kb
        )
    else:
        await message.answer("Quyidagi menyudan tanlang 👇", reply_markup=order_keyboard())

# ✅ Bitta handler yetadi (oldin 2 marta yozilgan edi)
@dp.message(F.contact)
async def contact_received(message: types.Message):
    uid = message.from_user.id
    raw_phone = message.contact.phone_number or ""
    phone = raw_phone if raw_phone.startswith("+") else f"+{raw_phone}"

    profile = user_profiles.get(uid, {})
    profile.update({"name": message.from_user.full_name, "phone": phone})
    user_profiles[uid] = profile
    await save_users_to_disk(user_profiles)

    # Onboardingning phone bosqichida bo'lsa — driver_onboarding ichiga ham yozib qo'yamiz
    if uid in driver_onboarding and driver_onboarding[uid].get("stage") == "phone":
        driver_onboarding[uid]["phone"] = phone
        await after_phone_collected(uid, message)
        return

    await message.answer("✅ Telefon raqamingiz saqlandi.", reply_markup=types.ReplyKeyboardRemove())
    await message.answer("Endi quyidagi menyudan tanlang 👇", reply_markup=order_keyboard())

# ================== BIZ BILAN BOG‘LANISH ==================
@dp.message(F.text == CONTACT_BTN)
async def contact_us(message: types.Message):
    caption = (
        "<b>📞 Biz bilan bog'lanish</b>\n\n"
        f"• Telefon: <a href=\"tel:{CONTACT_PHONE_LINK}\">{CONTACT_PHONE}</a>\n"
        f"• Telegram: @{CONTACT_TG}"
    )
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Telegramga yozish", url=f"https://t.me/{CONTACT_TG}")]
    ])
    sent = False
    if CONTACT_IMAGE_PATH and os.path.exists(CONTACT_IMAGE_PATH):
        try:
            await message.answer_photo(photo=FSInputFile(CONTACT_IMAGE_PATH), caption=caption, parse_mode="HTML", reply_markup=ikb)
            sent = True
        except Exception:
            sent = False
    if not sent and CONTACT_IMAGE_URL:
        try:
            await message.answer_photo(photo=CONTACT_IMAGE_URL, caption=caption, parse_mode="HTML", reply_markup=ikb)
            sent = True
        except Exception:
            sent = False
    if not sent:
        await message.answer(caption, parse_mode="HTML", reply_markup=ikb)

# ================== BUYURTMA FLOW (boshlash) ==================
@dp.message(Command("buyurtma"))
async def buyurtma_cmd(message: types.Message):
    await prompt_order_flow(message)

@dp.message(F.text == "🚖 Buyurtma berish")
async def buyurtma_btn(message: types.Message):
    await prompt_order_flow(message)

async def prompt_order_flow(message: types.Message):
    uid = message.from_user.id
    profile = user_profiles.get(uid)

    if not profile or not profile.get("phone"):
        await message.answer("Iltimos, telefon raqamingizni yuboring 📞", reply_markup=contact_keyboard())
        return

    drafts[uid] = {
        "stage": "region",
        "region": None,
        "chat_id": None,
        "vehicle": None,
        "from": None,
        "to": None,
        "when": None,
    }
    await message.answer(
        "📍 Qaysi hudud uchun buyurtma berasiz?",
        reply_markup=region_keyboard(show_back=False)
    )

@dp.message(F.text == CANCEL)
async def cancel_flow(message: types.Message):
    uid = message.from_user.id
    draft = drafts.get(uid)
    if draft:
        await remove_confirm_message(uid, draft)
    drafts.pop(uid, None)
    driver_onboarding.pop(uid, None)
    await message.answer("❌ Bekor qilindi.", reply_markup=order_keyboard())

# ================== HAYDOVCHI BO‘LISH (ESLATMA + ROZIMAN) ==================
@dp.message(F.text == DRIVER_BTN)
async def haydovchi_bolish(message: types.Message):
    uid = message.from_user.id
    drafts.pop(uid, None)
    driver_onboarding.pop(uid, None)

    if ESLATMA_IMAGE_PATH and os.path.exists(ESLATMA_IMAGE_PATH):
        try:
            await message.answer_photo(
                photo=FSInputFile(ESLATMA_IMAGE_PATH),
                caption="🔔 <b>ESLATMA</b>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    req_text = (
        "👨‍✈️ <b>Haydovchi uchun minimal talablar</b>\n"
        "1) Faol <b>oylik obuna</b> bo‘lishi shart.\n"
        "2) Soz avtomobil (Labo/Damas/Porter/…) va amal qiluvchi guvohnoma.\n"
        "3) Telegram/telefon doimo onlayn; xushmuomala va vaqtga rioya.\n\n"
        "📦 <b>Ish tartibi</b>\n"
        "1) Buyurtma guruhdan “Qabul qilish” orqali olinadi; <b>narx/vaqt/manzil</b> — haydovchi ↔ mijoz o‘rtasida <b>bevosita</b> kelishiladi.\n"
        "2) <b>EltiBer ma’muriyati</b> narx, to‘lov va yetkazish jarayoniga <b>aralashmaydi</b> va <b>javobgar emas</b>.\n"
        "3) Borolmasangiz — darhol mijozga xabar bering va bekor qiling.\n\n"
    )
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Shartlarga roziman", callback_data="driver_agree")]
    ])
    await message.answer(req_text, parse_mode="HTML", reply_markup=ikb)

@dp.callback_query(F.data == "driver_agree")
async def driver_agree_cb(callback: types.CallbackQuery):
    uid = callback.from_user.id
    driver_onboarding[uid] = {
        "stage": "regions",
        "regions": [],
        "name": None,
        "car_make": None,
        "car_plate": None,
        "phone": None,
    }
    await callback.message.answer(
        "📍 Qaysi hududlar uchun haydovchi bo‘lasiz?\n"
        "Bir nechta hududni ketma-ket tanlang. Tanlash tugagach “✅ Tanlash tugadi” tugmasini bosing."
        "\nHududni yana bosish orqali tanlovdan olib tashlashingiz mumkin.",
        reply_markup=driver_region_keyboard(include_back=False)
    )
    await callback.answer()

# ================== ONBOARDING MATN KOLLEKTORI ==================
@dp.message(F.text)
async def onboarding_or_order_text(message: types.Message):
    uid = message.from_user.id
    txt = (message.text or "").strip()

    if txt == BACK:
        await back_flow(message)
        return

    if uid in driver_onboarding:
        st = driver_onboarding[uid].get("stage")

        if st == "regions":
            regions_list = driver_onboarding[uid].setdefault("regions", [])
            if txt == REGION_DONE:
                if not regions_list:
                    await message.answer(
                        "❗️ Hech bo‘lmaganda bitta hududni tanlang.",
                        reply_markup=driver_region_keyboard(include_back=False)
                    )
                    return
                price_txt = format_price(compute_subscription_price(len(regions_list)))
                driver_onboarding[uid]["stage"] = "name"
                await message.answer(
                    "✅ Tanlov yakunlandi.\n"
                    f"📍 Hududlar: <b>{', '.join(regions_list)}</b>\n"
                    f"💳 Obuna to‘lovi: <b>{price_txt} so‘m</b> ({len(regions_list)} hudud)\n\n"
                    f"Maksimal {MAX_DRIVER_REGIONS} ta hudud tanlash mumkin."
                    "\nAgar ko‘proq hududga qo‘shilmoqchi bo‘lsangiz, ushbu jarayon yakunlangach yana “Haydovchi bo‘lish” bo‘limidan o‘ting."
                    "\n"
                    "✍️ Iltimos, <b>Ism Familiya</b>ingizni yuboring:",
                    parse_mode="HTML",
                    reply_markup=keyboard_with_back_cancel([], show_back=True)
                )
                return
            if txt == REGION_CLEAR:
                driver_onboarding[uid]["regions"] = []
                await message.answer(
                    "✅ Tanlov tozalandi.\n"
                    "Tanlangan hududlar: <b>—</b>\n"
                    f"💳 Jami to‘lov: <b>{format_price(0)}</b> so‘m\n"
                    "Yangi hududlarni tanlang.",
                    reply_markup=driver_region_keyboard(include_back=False)
                )
                return

            selected = resolve_region_name(txt)
            if not selected:
                await message.answer(
                    "❗️ Iltimos, hududni tugmalar yordamida tanlang.",
                    reply_markup=driver_region_keyboard(include_back=False)
                )
                return

            if selected not in regions_list and len(regions_list) >= MAX_DRIVER_REGIONS:
                await message.answer(
                    f"❗️ Bir vaqtning o‘zida faqat {MAX_DRIVER_REGIONS} ta hudud tanlash mumkin."
                    "\nHududni olib tashlash uchun tanlangan hudud ustiga yana bir marta bosing yoki “🗑 Tanlovni tozalash” tugmasidan foydalaning.",
                    reply_markup=driver_region_keyboard(include_back=False)
                )
                return

            if selected in regions_list:
                regions_list.remove(selected)
                price_txt = format_price(compute_subscription_price(len(regions_list)))
                await message.answer(
                    f"ℹ️ <b>{selected}</b> hududi tanlovdan olib tashlandi."
                    "\nTanlangan hududlar: <b>{all_regions}</b>\n"
                    "💳 Jami to‘lov: <b>{price}</b> so‘m\n"
                    "Yana hudud tanlang yoki “✅ Tanlash tugadi” tugmasini bosing."
                    .format(
                        all_regions=", ".join(regions_list) if regions_list else "—",
                        price=price_txt,
                    ),
                    parse_mode="HTML",
                    reply_markup=driver_region_keyboard(include_back=False)
                )
                return

            regions_list.append(selected)
            price_txt = format_price(compute_subscription_price(len(regions_list)))
            await message.answer(
                "✅ Hudud qo‘shildi: <b>{selected}</b>\n"
                "Tanlangan hududlar: <b>{all_regions}</b>\n"
                "💳 Jami to‘lov: <b>{price}</b> so‘m\n"
                "Yana hudud tanlang yoki “✅ Tanlash tugadi” tugmasini bosing."
                .format(
                    selected=selected,
                    all_regions=", ".join(regions_list),
                    price=price_txt,
                ),
                parse_mode="HTML",
                reply_markup=driver_region_keyboard(include_back=False)
            )
            return

        if st == "name":
            driver_onboarding[uid]["name"] = txt
            driver_onboarding[uid]["stage"] = "car_make"
            await message.answer("🚗 Avtomobil <b>markasi</b>ni yozing (masalan: Labo / Porter / Isuzu):", parse_mode="HTML", reply_markup=keyboard_with_back_cancel([], show_back=True))
            return

        if st == "car_make":
            driver_onboarding[uid]["car_make"] = txt
            driver_onboarding[uid]["stage"] = "car_plate"
            await message.answer("🔢 Avtomobil <b>davlat raqami</b>ni yozing (masalan: 01A123BC):", parse_mode="HTML", reply_markup=keyboard_with_back_cancel([], show_back=True))
            return

        if st == "car_plate":
            driver_onboarding[uid]["car_plate"] = txt
            driver_onboarding[uid]["stage"] = "phone"
            prof_phone = user_profiles.get(uid, {}).get("phone")
            hint = f"\n\nBizdagi saqlangan raqam: <b>{phone_display(prof_phone)}</b>" if prof_phone else ""
            await message.answer(
                "📞 Kontakt raqamingizni yuboring.\nRaqamni yozishingiz yoki pastdagi tugma orqali ulashishingiz mumkin." + hint,
                parse_mode="HTML",
                reply_markup=share_phone_keyboard()
            )
            return

        if st == "phone":
            phone = txt
            driver_onboarding[uid]["phone"] = phone if phone.startswith("+") else f"+{phone}"
            await after_phone_collected(uid, message)
            return

        return

    # Onboarding bo'lmasa — buyurtma oqimi
    await collect_flow(message)

# ================== YORDAMCHI (trial) — QO'SHIMCHA ==================
async def _send_trial_invites(uid: int, regions: list[str]):
    regions = normalize_region_list(regions)
    if not regions:
        return

    trial_region = regions[0]
    granted_at = datetime.now()
    expires_at = granted_at + timedelta(days=FREE_TRIAL_DAYS)

    profile = user_profiles.setdefault(uid, {})
    profile["trial_granted_at"] = granted_at.isoformat()
    profile["trial_expires_at"] = expires_at.isoformat()
    add_profile_regions(uid, regions)
    await save_users_to_disk(user_profiles)

    entry = trial_members.setdefault(uid, {"expires_at": expires_at, "regions": []})
    entry["expires_at"] = expires_at
    entry["regions"] = [trial_region]
    entry["last_region"] = trial_region

    text = (
        "🎁 <b>30 kunlik bepul sinov</b> faollashtirildi!\n\n"
        f"📍 Hudud: {trial_region}\n"
        f"⏳ Amal qilish muddati: <b>{expires_at.strftime('%Y-%m-%d %H:%M')}</b> gacha.\n"
        "Quyidagi tugma orqali guruhga qo‘shiling. Sinov tugaganda agar obuna bo‘lmasangiz, guruhdan chiqarib qo‘yiladi."
    )
    await send_region_invite(uid, trial_region, text)

    if len(regions) > 1:
        other_regions = ", ".join(regions[1:])
        try:
            await bot.send_message(
                uid,
                "ℹ️ Qolgan hududlar ({}) uchun obuna to‘lovi talab qilinadi."
                .format(other_regions),
            )
        except Exception:
            pass

async def trial_watcher():
    """
    Har soatda trial muddati tugaganlarni (to‘lov qilmagan bo‘lsa) guruhdan chiqaradi
    va to‘lov ma'lumotlari bilan DM yuboradi.
    """
    while True:
        try:
            now = datetime.now()
            for uid, info in list(trial_members.items()):
                # To'lov qilganlar kuzatuvdan chiqariladi
                if subscriptions.get(uid, {}).get("active"):
                    trial_members.pop(uid, None)
                    continue

                exp = info.get("expires_at")
                regions = normalize_region_list(info.get("regions"))
                if not regions:
                    regions = get_profile_regions(uid)

                if exp and now >= exp and regions:
                    driver_state = driver_onboarding.setdefault(uid, {})
                    driver_state["stage"] = "wait_check"
                    driver_state["regions"] = normalize_region_list(regions)

                    for region in regions:
                        try:
                            chat_id = get_driver_chat_id(region)
                        except Exception:
                            continue
                        try:
                            await bot.ban_chat_member(chat_id, uid)
                            await bot.unban_chat_member(chat_id, uid)
                        except Exception:
                            pass

                    price_value = compute_subscription_price(len(regions))
                    price_txt = format_price(price_value)
                    regions_text = ", ".join(regions)
                    pay_text = (
                        "⛔️ <b>30 kunlik bepul sinov muddati tugadi.</b>\n\n"
                        f"📍 <b>Hududlar:</b> {regions_text}\n"
                        f"💳 <b>Obuna to‘lovi:</b> <code>{price_txt} so‘m</code> ({len(regions)} hudud)\n"
                        f"🧾 <b>Karta:</b> <code>{CARD_NUMBER_DISPLAY}</code>\n"
                        f"👤 Karta egasi: <b>{CARD_HOLDER}</b>\n\n"
                        "✅ To‘lovni amalga oshirgach, <b>chek rasm</b>ini yuboring.\n"
                        "Tasdiqlangach, sizga <b>haydovchilar guruhiga</b> qayta qo‘shilish havolasini yuboramiz."
                    )

                    if SUPPORTS_COPY_TEXT:
                        ikb = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text="📋 Karta raqamini nusxalash",
                                        copy_text=CopyTextButton(text=CARD_NUMBER_DISPLAY)
                                    )
                                ],
                                [InlineKeyboardButton(text="📤 Chekni yuborish", callback_data="send_check")],
                            ]
                        )
                    else:
                        ikb = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [InlineKeyboardButton(text="📤 Chekni yuborish", callback_data="send_check")]
                            ]
                        )

                    try:
                        await bot.send_message(uid, pay_text, parse_mode="HTML", reply_markup=ikb)
                    except Exception:
                        pass

                    trial_members.pop(uid, None)

        except Exception:
            # watchdog yiqilmasin
            pass

        await asyncio.sleep(3600)  # 1 soatda bir tekshiradi

async def after_phone_collected(uid: int, message: types.Message):
    data = driver_onboarding.get(uid, {})
    name = data.get("name", "—")
    car_make = data.get("car_make", "—")
    car_plate = data.get("car_plate", "—")
    phone = data.get("phone", "—")
    regions = normalize_region_list(data.get("regions"))
    if not regions:
        regions = get_profile_regions(uid)

    if not regions:
        driver_onboarding.setdefault(uid, {})["stage"] = "regions"
        await message.answer(
            "📍 Iltimos, hududlarni tanlang.",
            reply_markup=driver_region_keyboard(include_back=False)
        )
        return

    driver_onboarding[uid]["regions"] = regions

    profile_entry = user_profiles.setdefault(uid, {})
    if phone and phone != "—":
        profile_entry["phone"] = phone
    if name and name != "—":
        profile_entry["name"] = profile_entry.get("name") or name
    set_profile_regions(uid, regions)
    await save_users_to_disk(user_profiles)

    profile = user_profiles.get(uid, {})
    trial_granted_at = profile.get("trial_granted_at")
    trial_joined_at = profile.get("trial_joined_at")

    sub_entry = subscriptions.get(uid) or {}
    has_active_sub = bool(sub_entry.get("active"))

    if FREE_TRIAL_ENABLED and not has_active_sub:
        if not trial_granted_at:
            try:
                await message.answer(
                    "🎁 Siz uchun <b>30 kunlik bepul sinov</b> ishga tushiriladi.\n"
                    "Bir zumda havolalarni yuboraman...",
                    parse_mode="HTML"
                )
            except Exception:
                pass
            await _send_trial_invites(uid, regions)
            driver_onboarding.pop(uid, None)
            return
        else:
            dt_txt = human_dt(trial_joined_at or trial_granted_at)
            try:
                await message.answer(
                    f"ℹ️ Siz {dt_txt} sanada 30 kunlik bepul sinov orqali haydovchilar guruhiga qo‘shilgansiz."
                    " Bepul sinov faqat bir martalik, shuning uchun qayta havola yuborilmaydi.",
                    parse_mode="HTML"
                )
            except Exception:
                pass

    elif has_active_sub:
        active_regions = set(normalize_region_list(sub_entry.get("regions")))
        new_regions = [r for r in regions if r not in active_regions]
        successful: list[str] = []
        for region in new_regions:
            text = (
                "✅ Sizning obunangiz faol.\n\n"
                f"📍 <b>Hudud:</b> {region}\n"
                "Quyidagi tugma orqali haydovchilar guruhiga qo‘shiling."
            )
            if await send_region_invite(uid, region, text):
                active_regions.add(region)
                successful.append(region)
        if active_regions:
            sub_entry["active"] = True
            normalized_active = normalize_region_list(active_regions)
            sub_entry["regions"] = normalized_active
            if normalized_active:
                sub_entry["last_region"] = normalized_active[-1]
        subscriptions[uid] = sub_entry
        if new_regions:
            if successful:
                driver_onboarding.pop(uid, None)
                return
            await message.answer(
                "❌ Silka yaratib bo‘lmadi. Iltimos, admin bilan bog‘laning yoki keyinroq qayta urinib ko‘ring.",
                reply_markup=order_keyboard()
            )
            driver_onboarding.pop(uid, None)
            return
        if not new_regions:
            await message.answer(
                "ℹ️ Tanlangan hududlar uchun obuna allaqachon faol.",
                reply_markup=order_keyboard()
            )
            driver_onboarding.pop(uid, None)
            return

    price_value = compute_subscription_price(len(regions))
    price_txt = format_price(price_value)
    pay_text = (
        f"💳 <b>Obuna to‘lovi:</b> <code>{price_txt} so‘m</code> ({len(regions)} hudud)\n"
        f"🧾 <b>Karta:</b> <code>{CARD_NUMBER_DISPLAY}</code>\n"
        f"👤 Karta egasi: <b>{CARD_HOLDER}</b>\n\n"
        "✅ To‘lovni amalga oshirgach, <b>chek rasm</b>ini yuboring (screenshot ham bo‘ladi).\n"
        "⚠️ <b>Ogohlantirish:</b> soxtalashtirilgan chek yuborgan shaxsga <b>jinoyiy javobgarlik</b> qo‘llanilishi mumkin."
    )

    if SUPPORTS_COPY_TEXT:
        ikb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📋 Karta raqamini nusxalash",
                        copy_text=CopyTextButton(text=CARD_NUMBER_DISPLAY)
                    )
                ],
                [InlineKeyboardButton(text="📤 Chekni yuborish", callback_data="send_check")],
            ]
        )
    else:
        ikb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📤 Chekni yuborish", callback_data="send_check")]
            ]
        )

    regions_text = ", ".join(regions)
    await message.answer(
        "Ma’lumotlaringiz qabul qilindi ✅\n\n"
        f"👤 <b>F.I.Sh:</b> {name}\n"
        f"🚗 <b>Avtomobil:</b> {car_make}\n"
        f"🔢 <b>Raqam:</b> {car_plate}\n"
        f"📞 <b>Telefon:</b> {phone_display(user_profiles.get(uid, {}).get('phone', phone))}\n"
        f"📍 <b>Hudud(lar):</b> {regions_text}",
        parse_mode="HTML"
    )

    needs_payment = len(regions) > 1 or has_active_sub

    if needs_payment:
        await message.answer(pay_text, parse_mode="HTML", reply_markup=ikb)
        driver_onboarding[uid]["stage"] = "wait_check"
        driver_onboarding[uid]["regions"] = regions
    else:
        await message.answer(
            "🎁 30 kunlik trial faollashtirildi. Trial tugaguncha tashkilotchi siz bilan bog‘lanadi."
        )
        driver_onboarding.pop(uid, None)

@dp.callback_query(F.data == "send_check")
async def send_check_cb(callback: types.CallbackQuery):
    uid = callback.from_user.id
    if uid not in driver_onboarding:
        await callback.answer(); return
    driver_onboarding[uid]["stage"] = "wait_check"
    await callback.message.answer("📸 Iltimos, <b>chek rasmini</b> bitta rasm ko‘rinishida yuboring (screenshot ham bo‘ladi).", parse_mode="HTML")
    await callback.answer()

# ================== CHEK LOGIKA: caption & yuborish helperlari ==================
def _make_payment_kb(driver_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"payok_{driver_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"payno_{driver_id}")
        ]
    ])

async def _build_check_caption(uid: int, data: dict) -> str:
    name      = data.get("name", "—")
    car_make  = data.get("car_make", "—")
    car_plate = data.get("car_plate", "—")
    phone     = data.get("phone", "—")
    regions   = data.get("regions") or data.get("region")
    region_list = normalize_region_list(regions)
    if not region_list:
        region_list = resolve_driver_regions(uid)
    if not region_list:
        region_list = ["—"]
    else:
        data["regions"] = region_list
    region_text = ", ".join(region_list)
    price_value = compute_subscription_price(len([r for r in region_list if r != "—"]))
    price_txt = format_price(price_value)
    cap = (
        "🧾 <b>Yangi obuna to‘lovi (haydovchi)</b>\n"
        f"👤 <b>F.I.Sh:</b> {name}\n"
        f"🚗 <b>Avtomobil:</b> {car_make}\n"
        f"🔢 <b>Raqam:</b> {car_plate}\n"
        f"📞 <b>Telefon:</b> {phone}\n"
        f"📍 <b>Hudud(lar):</b> {region_text}\n"
        f"🔗 <b>Profil:</b> <a href=\"tg://user?id={uid}\">{uid}</a>\n\n"
        f"💳 <b>Miqdor:</b> {price_txt} so‘m\n"
        "⚠️ <i>Ogohlantirish: soxtalashtirilgan chek yuborgan shaxsga nisbatan "
        "jinoyiy javobgarlik qo‘llanilishi mumkin.</i>"
    ).replace(",", " ")
    return cap

async def _send_check_to_payments(uid: int, caption: str, file_id: str, as_photo: bool) -> bool:
    kb = _make_payment_kb(uid)
    try:
        if as_photo:
            await bot.send_photo(chat_id=PAYMENTS_CHAT_ID, photo=file_id, caption=caption, parse_mode="HTML", reply_markup=kb)
        else:
            await bot.send_document(chat_id=PAYMENTS_CHAT_ID, document=file_id, caption=caption, parse_mode="HTML", reply_markup=kb)
        return True
    except Exception as e:
        err = str(e).lower()
        if as_photo and "not enough rights to send photos" in err:
            try:
                await bot.send_document(chat_id=PAYMENTS_CHAT_ID, document=file_id, caption=caption, parse_mode="HTML", reply_markup=kb)
                return True
            except Exception as e2:
                e = e2

        note = ("\n\n⚠️ Chekni cheklar guruhiga yuborib bo‘lmadi. "
                "Guruh ruxsatlarini tekshiring yoki bu xabarni oldinga yuboring.")
        for admin in ADMIN_IDS:
            try:
                if as_photo:
                    await bot.send_photo(admin, file_id, caption=caption + note, parse_mode="HTML")
                else:
                    await bot.send_document(admin, file_id, caption=caption + note, parse_mode="HTML")
            except Exception:
                pass
        warn = f"❗️ Chekni cheklar guruhiga yuborib bo‘lmadi.\nUser: {uid}\nXato: {e}"
        for admin in ADMIN_IDS:
            try: await bot.send_message(admin, warn)
            except Exception: pass
        return False

# FOTO (gallery yoki screenshot)
@dp.message(F.photo)
async def receive_check_photo(message: types.Message):
    uid = message.from_user.id
    if uid not in driver_onboarding or driver_onboarding[uid].get("stage") != "wait_check":
        return
    data = driver_onboarding.get(uid, {})
    file_id = message.photo[-1].file_id
    caption = await _build_check_caption(uid, data)
    ok = await _send_check_to_payments(uid, caption, file_id, as_photo=True)
    if not ok:
        await message.answer("❌ Chekni log guruhiga yuborishda xatolik. Iltimos, keyinroq qayta urinib ko‘ring yoki admin bilan bog‘laning.")
        return
    await message.answer(
        "✅ Chek yuborildi. Iltimos, <b>tasdiqlashni kuting</b>.\n"
        "Tasdiqlangandan so‘ng <b>admin sizga Haydovchilar guruhi</b> silkasini yuboradi.",
        parse_mode="HTML",
        reply_markup=order_keyboard()
    )
    driver_onboarding.pop(uid, None)

# FAYL (document) sifatida — image/* bo‘lsa ham, bo‘lmasa ham
@dp.message(F.document)
async def receive_check_document(message: types.Message):
    uid = message.from_user.id
    if uid not in driver_onboarding or driver_onboarding[uid].get("stage") != "wait_check":
        return
    doc = message.document
    file_id = doc.file_id
    data = driver_onboarding.get(uid, {})
    caption = await _build_check_caption(uid, data)
    ok = await _send_check_to_payments(uid, caption, file_id, as_photo=False)
    if not ok:
        await message.answer("❌ Chekni log guruhiga yuborishda xatolik. Iltimos, keyinroq qayta urinib ko‘ring yoki admin bilan bog‘laning.")
        return
    await message.answer(
        "✅ Chek yuborildi. Iltimos, <b>tasdiqlashni kuting</b>.\n"
        "Tasdiqlangandan so‘ng <b>admin sizga Haydovchilar guruhi</b> silkasini yuboradi.",
        parse_mode="HTML",
        reply_markup=order_keyboard()
    )
    driver_onboarding.pop(uid, None)

# ================== ADMIN: Tasdiqlash/Rad etish tugmalari callbacklari ==================
async def _send_driver_invite_and_mark(callback: types.CallbackQuery, driver_id: int):
    regions = normalize_region_list(resolve_driver_regions(driver_id))
    if not regions:
        await callback.answer(
            "Haydovchining hududlari aniqlanmadi. Iltimos, hududlarni qayta tanlang.",
            show_alert=True,
        )
        return

    sent_any = False
    for region in regions:
        text = (
            "✅ <b>To‘lov tasdiqlandi.</b>\n\n"
            f"📍 <b>Hudud:</b> {region}\n"
            "Quyidagi tugma orqali haydovchilar guruhiga qo‘shiling. "
            "Guruhga qo‘shilgandan so‘ng bu xabar avtomatik o‘chiriladi."
        )
        ok = await send_region_invite(driver_id, region, text)
        sent_any = sent_any or ok

    if not sent_any:
        await callback.answer("❌ Silka yuborilmadi. Iltimos, keyinroq qayta urinib ko‘ring.", show_alert=True)
        return

    normalized_regions = normalize_region_list(regions)
    subscription_entry = {"active": True, "regions": normalized_regions}
    if normalized_regions:
        subscription_entry["last_region"] = normalized_regions[-1]
    subscriptions[driver_id] = subscription_entry
    trial_members.pop(driver_id, None)

    # Cheklar guruhidagi xabarni 'Tasdiqlandi' deb yangilash va tugmalarni o‘chirish
    try:
        orig_cap = callback.message.caption or ""
        admin_name = callback.from_user.username or callback.from_user.full_name
        price_txt = format_price(compute_subscription_price(len(normalized_regions)))
        new_cap = (
            f"{orig_cap}\n\n✅ <b>Tasdiqlandi</b> — {admin_name} • {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            f"\n📍 Hududlar: {', '.join(normalized_regions)}"
            f"\n💳 To‘lov: {price_txt} so‘m"
        )
        await bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=new_cap,
            parse_mode="HTML",
            reply_markup=None
        )
    except Exception:
        try:
            await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=None)
        except Exception:
            pass

    await callback.answer("✅ Tasdiqlandi va silka yuborildi.")

@dp.callback_query(F.data.startswith("payok_"))
async def cb_payment_ok(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Faqat admin tasdiqlashi mumkin.", show_alert=True)
        return
    try:
        driver_id = int(callback.data.split("_")[1])
    except Exception:
        await callback.answer("Xato ID.", show_alert=True); return

    await _send_driver_invite_and_mark(callback, driver_id)

@dp.callback_query(F.data.startswith("payno_"))
async def cb_payment_no(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Faqat admin rad etishi mumkin.", show_alert=True)
        return
    try:
        driver_id = int(callback.data.split("_")[1])
    except Exception:
        await callback.answer("Xato ID.", show_alert=True); return

    # Haydovchiga rad etilganiga doir DM
    try:
        await bot.send_message(
            driver_id,
            "❌ To‘lovingiz <b>rad etildi</b>.\n"
            "Iltimos, to‘g‘ri va aniq chek rasmini qaytadan yuboring.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    # Postni yangilash va tugmalarni olib tashlash
    try:
        orig_cap = callback.message.caption or ""
        admin_name = callback.from_user.username or callback.from_user.full_name
        new_cap = f"{orig_cap}\n\n❌ <b>Rad etildi</b> — {admin_name} • {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        await bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=new_cap,
            parse_mode="HTML",
            reply_markup=None
        )
    except Exception:
        try:
            await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=None)
        except Exception:
            pass

    await callback.answer("Rad etildi.")

# ================== ADMIN: /tasdiq <user_id> (qo‘lda variant) ==================
@dp.message(Command("tasdiq"))
async def admin_confirm_payment(message: types.Message):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS:
        return

    parts = (message.text or "").strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.reply("Foydalanish: <code>/tasdiq USER_ID</code>", parse_mode="HTML")
        return

    driver_id = int(parts[1])
    regions = resolve_driver_regions(driver_id)
    if not regions:
        await message.reply("❌ Haydovchining hududlari aniqlanmadi. Avval haydovchi hududlarni tanlashi kerak.")
        return

    sent_any = False
    for region in regions:
        text = (
            "✅ <b>To‘lov tasdiqlandi.</b>\n\n"
            f"📍 <b>Hudud:</b> {region}\n"
            "Quyidagi tugma orqali haydovchilar guruhiga qo‘shiling. "
            "Guruhga qo‘shilgandan so‘ng bu xabar avtomatik o‘chiriladi."
        )
        ok = await send_region_invite(driver_id, region, text)
        sent_any = sent_any or ok

    if sent_any:
        normalized = normalize_region_list(regions)
        sub_entry = {"active": True, "regions": normalized}
        if normalized:
            sub_entry["last_region"] = normalized[-1]
        subscriptions[driver_id] = sub_entry
        trial_members.pop(driver_id, None)
        await message.reply(
            "✅ Silka(l)ar yuborildi: {regions}\n"
            "💳 To‘lov: {price} so‘m".format(
                regions=", ".join(normalized),
                price=format_price(compute_subscription_price(len(normalized))),
            ),
            parse_mode="HTML",
        )
    else:
        await message.reply("❌ Haydovchiga DM yuborilmadi (botga /start yozmagan bo‘lishi mumkin).")

# ================== CHAT MEMBER UPDATE: guruhga qo‘shilganda DM’ni o‘chirish ==================
@dp.chat_member()
async def on_chat_member(update: types.ChatMemberUpdated):
    try:
        chat_id = update.chat.id
        if chat_id not in DRIVER_CHAT_ID_SET:
            return
        old_status = update.old_chat_member.status
        new_status = update.new_chat_member.status
        user = update.new_chat_member.user
        if new_status in ("member", "administrator") and old_status in ("left", "kicked"):
            pend_map = pending_invites.get(user.id) or {}
            matched_region = None
            matched_info = None
            if isinstance(pend_map, dict):
                for region_key, info in list(pend_map.items()):
                    if info.get("chat_id") == chat_id:
                        matched_region = region_key
                        matched_info = info
                        del pend_map[region_key]
                if pend_map:
                    pending_invites[user.id] = pend_map
                elif user.id in pending_invites:
                    pending_invites.pop(user.id, None)

            if matched_info and matched_info.get("msg_id"):
                try:
                    await bot.delete_message(chat_id=user.id, message_id=matched_info["msg_id"])
                except Exception:
                    pass
            if matched_region:
                try:
                    await bot.send_message(user.id, "🎉 Guruhga muvaffaqiyatli qo‘shildingiz! Ishingizga omad.")
                except Exception:
                    pass

            region = matched_region or DRIVER_CHAT_ID_TO_REGION.get(chat_id)
            profile = user_profiles.setdefault(user.id, {})
            if region:
                add_profile_regions(user.id, [region])
                sub_entry = subscriptions.setdefault(user.id, {})
                if sub_entry.get("active"):
                    sub_entry["regions"] = normalize_region_list(sub_entry.get("regions") or [region])
                trial_entry = trial_members.get(user.id)
                if trial_entry:
                    trial_entry["regions"] = normalize_region_list(trial_entry.get("regions") or [region])
            if profile.get("trial_granted_at") and not profile.get("trial_joined_at"):
                profile["trial_joined_at"] = datetime.now().isoformat()
                await save_users_to_disk(user_profiles)
    except Exception:
        pass

# ================== ORTGA (onboarding + buyurtma) ==================
@dp.message(F.text == BACK)
async def back_flow(message: types.Message):
    uid = message.from_user.id

    # Onboarding ortga
    if uid in driver_onboarding:
        st = driver_onboarding[uid].get("stage")
        if st == "regions":
            driver_onboarding.pop(uid, None)
            await message.answer("Asosiy menyu", reply_markup=order_keyboard()); return
        if st == "name":
            driver_onboarding[uid]["stage"] = "regions"
            driver_onboarding[uid]["name"] = None
            await message.answer(
                "📍 Qaysi hududlar uchun haydovchi bo‘lasiz?",
                reply_markup=driver_region_keyboard(include_back=False)
            ); return
        if st == "car_make":
            driver_onboarding[uid]["stage"] = "name"
            await message.answer("✍️ Iltimos, <b>Ism Familiya</b>ingizni yuboring:", parse_mode="HTML", reply_markup=keyboard_with_back_cancel([], show_back=True)); return
        if st == "car_plate":
            driver_onboarding[uid]["stage"] = "car_make"
            await message.answer("🚗 Avtomobil <b>markasi</b>ni yozing:", parse_mode="HTML", reply_markup=keyboard_with_back_cancel([], show_back=True)); return
        if st == "phone":
            driver_onboarding[uid]["stage"] = "car_plate"
            await message.answer("🔢 Avtomobil <b>davlat raqami</b>ni yozing:", parse_mode="HTML", reply_markup=keyboard_with_back_cancel([], show_back=True)); return
        if st == "wait_check":
            await after_phone_collected(uid, message); return

    # Buyurtma ortga
    d = drafts.get(uid)
    if not d:
        await message.answer("Asosiy menyu", reply_markup=order_keyboard()); return

    stage = d["stage"]

    # Soddalashtirilgan bosqichlar:
    if stage == "region":
        drafts.pop(uid, None)
        await message.answer("Asosiy menyu", reply_markup=order_keyboard()); return
    if stage == "vehicle":
        if d.get("region"):
            d["stage"] = "region"
            d["vehicle"] = None
            d["region"] = None
            d["chat_id"] = None
            await message.answer(
                "📍 Qaysi hudud uchun buyurtma berasiz?",
                reply_markup=region_keyboard(show_back=False)
            ); return
        drafts.pop(uid, None)
        await message.answer("Asosiy menyu", reply_markup=order_keyboard()); return
    if stage == "confirm":
        await remove_confirm_message(uid, d)
        d["stage"] = "when_select"
        await message.answer(
            "🕒 Qaysi **vaqtga** kerak?\nTugmalardan tanlang yoki `HH:MM` yozing.",
            reply_markup=when_keyboard()
        ); return
    if stage == "from":
        d["stage"] = "vehicle"
        d["vehicle"] = None
        await message.answer("🚚 Qanday yuk mashinasi kerak?\nQuyidagidan tanlang yoki o‘zingiz yozing:", reply_markup=vehicle_keyboard()); return
    if stage == "to":
        d["stage"] = "from"
        d["from"] = None
        await message.answer("📍 Yuk **qayerdan** olinadi?\nManzilni yozing yoki “📍 Lokatsiyani yuborish” tugmasi:", reply_markup=pickup_keyboard()); return
    if stage == "when_select":
        d["stage"] = "to"
        d["when"] = None
        await message.answer("📦 Yuk **qayerga** yetkaziladi? Manzilni yozing:", reply_markup=keyboard_with_back_cancel([], show_back=True)); return
    if stage == "when_input":
        d["stage"] = "when_select"
        await message.answer("🕒 Qaysi **vaqtga** kerak?\nTugmalardan tanlang yoki `HH:MM` yozing.", reply_markup=when_keyboard()); return

# ================== BUYURTMA: LOKATSIYA ==================
@dp.message(F.location)
async def location_received(message: types.Message):
    uid = message.from_user.id
    if uid not in drafts: return
    d = drafts[uid]
    if d.get("stage") != "from": return
    lat = message.location.latitude
    lon = message.location.longitude
    d["from"] = f"https://maps.google.com/?q={lat},{lon}"
    d["stage"] = "to"
    await message.answer("✅ Lokatsiya qabul qilindi.\n\n📦 Endi yuk **qayerga** yetkaziladi? Manzilni yozing:", reply_markup=keyboard_with_back_cancel([], show_back=True))

# ================== BUYURTMA KOLLEKTOR ==================
async def collect_flow(message: types.Message):
    uid = message.from_user.id
    if uid not in drafts:
        return
    d = drafts[uid]
    stage = d["stage"]
    text = (message.text or "").strip()

    if stage == "region":
        selected = resolve_region_name(text)
        if not selected:
            await message.answer(
                "❗️ Iltimos, hududni tugmalar yordamida tanlang.",
                reply_markup=region_keyboard(show_back=False)
            )
            return
        await remove_confirm_message(uid, d)
        d["region"] = selected
        d["chat_id"] = get_order_chat_id(selected)
        user_profiles.setdefault(uid, {})["last_region"] = selected
        await save_users_to_disk(user_profiles)
        d["stage"] = "vehicle"
        await message.answer(
            "🚚 Qanday yuk mashinasi kerak?\nQuyidagidan tanlang yoki o‘zingiz yozing:",
            reply_markup=vehicle_keyboard()
        )
        return

    if stage == "vehicle":
        await remove_confirm_message(uid, d)
        d["vehicle"] = text if text else "Noma'lum"
        d["stage"] = "from"
        await message.answer(
            "📍 Yuk **qayerdan** olinadi?\nManzilni yozing yoki “📍 Lokatsiyani yuborish”:",
            reply_markup=pickup_keyboard()
        )
        return

    if stage == "from":
        await remove_confirm_message(uid, d)
        d["from"] = text
        d["stage"] = "to"
        await message.answer(
            "📦 Yuk **qayerga** yetkaziladi? Manzilni yozing:",
            reply_markup=keyboard_with_back_cancel([], show_back=True)
        )
        return

    if stage == "to":
        await remove_confirm_message(uid, d)
        d["to"] = text
        d["stage"] = "when_select"
        await message.answer(
            "🕒 Qaysi **vaqtga** kerak?\nTugmalardan tanlang yoki `HH:MM` yozing.",
            reply_markup=when_keyboard()
        )
        return

    if stage == "when_select":
        await remove_confirm_message(uid, d)
        if text == HOZIR:
            d["when"] = datetime.now().strftime("%H:%M")
            d["stage"] = "confirm"
            await send_draft_confirmation(uid, message, d)
            return
        if text == BOSHQA:
            d["stage"] = "when_input"
            await message.answer(
                "⏰ Vaqtni kiriting (`HH:MM`, masalan: `19:00`):",
                reply_markup=keyboard_with_back_cancel([], show_back=True)
            )
            return
        if is_hhmm(text):
            d["when"] = normalize_hhmm(text)
            d["stage"] = "confirm"
            await send_draft_confirmation(uid, message, d)
            return
        await message.answer(
            "❗️ Vaqt formati `HH:MM` bo‘lishi kerak. Yoki tugmalarni tanlang.",
            reply_markup=when_keyboard()
        )
        return

    if stage == "when_input":
        await remove_confirm_message(uid, d)
        if is_hhmm(text):
            d["when"] = normalize_hhmm(text)
            d["stage"] = "confirm"
            await send_draft_confirmation(uid, message, d)
            return
        await message.answer(
            "❗️ Noto‘g‘ri format. `HH:MM` yozing (masalan: `19:00`).",
            reply_markup=keyboard_with_back_cancel([], show_back=True)
        )
        return

    if stage == "confirm":
        await message.answer(
            "ℹ️ Iltimos, buyurtmani tasdiqlash uchun pastdagi tugmalarni bosing yoki 'Ortga' tugmasidan foydalaning."
        )
        return

# ================== YORDAMCHI (buyurtma) ==================
def is_hhmm(s: str) -> bool:
    try:
        datetime.strptime(s, "%H:%M"); return True
    except Exception:
        return False

def normalize_hhmm(s: str) -> str:
    try:
        t = datetime.strptime(s, "%H:%M").time(); return t.strftime("%H:%M")
    except Exception:
        return s

def phone_display(p: str) -> str:
    if not p: return "—"
    p = str(p); return p if p.startswith("+") else f"+{p}"

def human_dt(dt_str: str | None) -> str:
    if not dt_str:
        return "—"
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return dt_str

def group_post_text(customer_id: int, order: dict, status_note: str | None = None) -> str:
    customer_name = user_profiles.get(customer_id, {}).get("name", "Mijoz")
    region = order.get("region", "—")
    base = (
        f"📦 Yangi buyurtma!\n"
        f"👤 Mijoz: {customer_name}\n"
        f"📍 Hudud: {region}\n"
        f"🚚 Mashina: {order['vehicle']}\n"
        f"➡️ Yo‘nalish:\n"
        f"   • Qayerdan: {order['from']}\n"
        f"   • Qayerga: {order['to']}\n"
        f"🕒 Vaqt: {order['when']}\n"
        f"ℹ️ Telefon raqami guruhda ko‘rsatilmaydi."
    )
    if status_note: base += f"\n{status_note}"
    return base

def _event_dt_today_or_now(hhmm: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    try:
        h, m = map(int, hhmm.split(":"))
        target = datetime.combine(now.date(), dtime(hour=h, minute=m))
    except Exception:
        return now
    return target if target > now else now

async def _sleep_and_notify(delay_sec: float, chat_id: int, text: str):
    try:
        if delay_sec > 0: await asyncio.sleep(delay_sec)
        await bot.send_message(chat_id, text, disable_web_page_preview=True)
    except asyncio.CancelledError:
        return
    except Exception:
        pass

def cancel_driver_reminders(customer_id: int):
    order = orders.get(customer_id)
    if not order: return
    tasks = order.get("reminder_tasks") or []
    for t in tasks:
        try: t.cancel()
        except Exception: pass
    order["reminder_tasks"] = []

def schedule_driver_reminders(customer_id: int):
    order = orders.get(customer_id)
    if not order or order.get("status") != "accepted": return
    driver_id = order.get("driver_id")
    if not driver_id: return

    cancel_driver_reminders(customer_id)
    now = datetime.now()
    event_dt = _event_dt_today_or_now(order["when"], now=now)
    seconds_to_event = (event_dt - now).total_seconds()
    milestones = [(3600, "⏳ 1 soat qoldi"), (1800, "⏳ 30 daqiqa qoldi"), (900, "⏳ 15 daqiqa qoldi"), (0, "⏰ Vaqti bo‘ldi")]
    base = (
        f"{order['when']} vaqti uchun {order.get('region', 'Hudud')} buyurtma.\n"
        f"Yo‘nalish: {order['from']} → {order['to']}\n"
        "Muvofiqlashtirishni unutmang."
    )
    order["reminder_tasks"] = []
    for offset, label in milestones:
        delay = seconds_to_event - offset
        if delay < 0: continue
        text = f"{label} — {base}"
        task = asyncio.create_task(_sleep_and_notify(delay, driver_id, text))
        order["reminder_tasks"].append(task)


def build_draft_summary(d: dict) -> str:
    region = d.get("region", "—")
    return (
        "📋 <b>Buyurtma ma'lumotlari</b>\n\n"
        f"📍 Hudud: {region}\n"
        f"🚚 Mashina: {d.get('vehicle', '—')}\n"
        f"📍 Qayerdan: {d.get('from', '—')}\n"
        f"📦 Qayerga: {d.get('to', '—')}\n"
        f"🕒 Vaqt: {d.get('when', '—')}"
    )


async def send_draft_confirmation(uid: int, message: types.Message, d: dict) -> None:
    summary = build_draft_summary(d)
    ikb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"draft_confirm_{uid}")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"draft_cancel_{uid}")],
        ]
    )
    sent = await message.answer(summary, parse_mode="HTML", reply_markup=ikb)
    d["confirm_msg_id"] = sent.message_id


async def remove_confirm_message(uid: int, d: dict) -> None:
    msg_id = d.pop("confirm_msg_id", None)
    if msg_id:
        try:
            await bot.delete_message(chat_id=uid, message_id=msg_id)
        except Exception:
            pass

# ================== GURUHGA YUBORISH + MIJOZGA BEKOR TUGMASI ==================
async def finalize_and_send(message_or_uid, d: dict):
    if isinstance(message_or_uid, types.Message):
        message = message_or_uid
        uid = message.from_user.id
    else:
        message = None
        uid = int(message_or_uid)

    profile = user_profiles.get(uid, {})
    region = d.get("region") or profile.get("last_region")
    if not region:
        profile_regions = get_profile_regions(uid)
        if profile_regions:
            region = profile_regions[-1]
    if not region:
        drafts[uid] = d
        prompt = "📍 Iltimos, hududni tanlang."
        if message:
            await message.answer(prompt, reply_markup=region_keyboard(show_back=False))
        else:
            await bot.send_message(uid, prompt, reply_markup=region_keyboard(show_back=False))
        return

    chat_id = d.get("chat_id") or get_order_chat_id(region)
    order_data = {
        "region": region,
        "vehicle": d["vehicle"],
        "from": d["from"],
        "to": d["to"],
        "when": d["when"],
    }
    ikb_group = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❗️ Qabul qilish", callback_data=f"accept_{uid}")]
    ])
    sent = await bot.send_message(chat_id, group_post_text(uid, order_data), reply_markup=ikb_group)
    orders[uid] = {
        **order_data,
        "msg_id": sent.message_id,
        "chat_id": chat_id,
        "status": "open",
        "driver_id": None,
        "cust_info_msg_id": None,
        "drv_info_msg_id": None,
        "cust_rating_msg_id": None,
        "rating": None,
        "reminder_tasks": [],
    }
    ikb_cust = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Buyurtmani bekor qilish", callback_data=f"cancel_{uid}")]]
    )
    notify = "✅ Buyurtma haydovchilarga yuborildi.\nKerak bo‘lsa bekor qilishingiz mumkin."
    if message:
        await message.answer(notify, reply_markup=ikb_cust)
        await message.answer("Asosiy menyu", reply_markup=order_keyboard())
    else:
        await bot.send_message(uid, notify, reply_markup=ikb_cust)
        await bot.send_message(uid, "Asosiy menyu", reply_markup=order_keyboard())
    drafts.pop(uid, None)

# ================== DRAFT TASDIQLASH CALLBACKLARI ==================
@dp.callback_query(F.data.startswith("draft_confirm_"))
async def draft_confirm_callback(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 3 or not parts[2].isdigit():
        await callback.answer("Xato ID.", show_alert=True)
        return
    target_id = int(parts[2])
    uid = callback.from_user.id
    if uid != target_id:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return

    draft = drafts.get(uid)
    if not draft or draft.get("stage") != "confirm":
        await callback.answer("Aktiv buyurtma topilmadi.", show_alert=True)
        return

    await remove_confirm_message(uid, draft)

    await finalize_and_send(uid, draft)
    await callback.answer("Buyurtma yuborildi!")


@dp.callback_query(F.data.startswith("draft_cancel_"))
async def draft_cancel_callback(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 3 or not parts[2].isdigit():
        await callback.answer("Xato ID.", show_alert=True)
        return
    target_id = int(parts[2])
    uid = callback.from_user.id
    if uid != target_id:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return

    draft = drafts.get(uid)
    if draft:
        await remove_confirm_message(uid, draft)
    drafts.pop(uid, None)

    await bot.send_message(uid, "❌ Buyurtma bekor qilindi.", reply_markup=order_keyboard())
    await callback.answer("Bekor qilindi.")

# ================== QABUL / YAKUN / BAHO / BEKOR ==================
@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: types.CallbackQuery):
    try: customer_id = int(callback.data.split("_")[1])
    except Exception:
        await callback.answer("Xato ID.", show_alert=True); return

    order = orders.get(customer_id); customer = user_profiles.get(customer_id)
    if not order or not customer:
        await callback.answer("Bu buyurtma topilmadi yoki allaqachon yakunlangan.", show_alert=True); return
    if order.get("status") != "open":
        await callback.answer("Bu buyurtma allaqachon qabul qilingan yoki yakunlangan.", show_alert=True); return

    driver_id = callback.from_user.id
    driver = user_profiles.get(driver_id)
    if not driver or not driver.get("phone"):
        await bot.send_message(driver_id, "ℹ️ Buyurtmani qabul qilishdan oldin telefon raqamingizni yuboring.", reply_markup=contact_keyboard())
        await callback.answer("Avval telefon raqamingizni yuboring.", show_alert=True); return

    order_region = order.get("region")
    driver_regions = resolve_driver_regions(driver_id)
    if order_region:
        if driver_regions and order_region not in driver_regions:
            await callback.answer(
                "Bu buyurtma {region} hududi uchun. Siz tanlagan hududlar: {selected}.".format(
                    region=order_region,
                    selected=", ".join(driver_regions),
                ),
                show_alert=True,
            )
            return
        if not driver_regions:
            add_profile_regions(driver_id, [order_region])
            driver_regions = [order_region]

    chat_id = order.get("chat_id") or get_order_chat_id(order_region)

    order["status"] = "accepted"; order["driver_id"] = driver_id

    customer_name, customer_phone = customer.get("name", "Noma'lum"), customer.get("phone", "—")
    driver_name, driver_phone     = driver.get("name", callback.from_user.full_name), driver.get("phone", "—")

    txt_drv = (
        f"✅ Buyurtma sizga biriktirildi\n\n"
        f"👤 Mijoz: {customer_name}\n"
        f"📞 Telefon: <a href=\"tg://user?id={customer_id}\">{phone_display(customer_phone)}</a>\n"
        f"📍 Hudud: {order_region}\n"
        f"🚚 Mashina: {order['vehicle']}\n"
        f"➡️ Yo‘nalish:\n   • Qayerdan: {order['from']}\n"
        f"   • Qayerga: {order['to']}\n"
        f"🕒 Vaqt: {order['when']}"
    )
    ikb_drv = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Buyurtmani yakunlash", callback_data=f"complete_{customer_id}")],
        [InlineKeyboardButton(text="❌ Buyurtmani bekor qilish", callback_data=f"cancel_{customer_id}")],
        [InlineKeyboardButton(text="👤 Mijoz profili", url=f"tg://user?id={customer_id}")]
    ])
    try:
        drv_msg = await bot.send_message(driver_id, txt_drv, parse_mode="HTML", disable_web_page_preview=True, reply_markup=ikb_drv)
        order["drv_info_msg_id"] = drv_msg.message_id
    except Exception:
        await callback.answer("Haydovchiga DM yuborilmadi. Botga /start yozing.", show_alert=True); return

    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=order["msg_id"], text=group_post_text(customer_id, order, status_note="✅ Holat: QABUL QILINDI"))
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=order["msg_id"], reply_markup=None)
    except Exception:
        pass

    txt_cust = (
        f"🚚 Buyurtmangizni haydovchi qabul qildi.\n\n"
        f"👨‍✈️ Haydovchi: {driver_name}\n"
        f"📞 Telefon: <a href=\"tg://user?id={driver_id}\">{phone_display(driver_phone)}</a>\n"
        f"📍 Hudud: {order_region}"
    )
    ikb_cust = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Buyurtmani bekor qilish", callback_data=f"cancel_{customer_id}")],
        [InlineKeyboardButton(text="👨‍✈️ Haydovchi profili", url=f"tg://user?id={driver_id}")]
    ])
    try:
        cust_msg = await bot.send_message(customer_id, txt_cust, parse_mode="HTML", disable_web_page_preview=True, reply_markup=ikb_cust)
        order["cust_info_msg_id"] = cust_msg.message_id
    except Exception:
        pass

    schedule_driver_reminders(customer_id)
    await callback.answer("Buyurtma sizga biriktirildi!")

@dp.callback_query(F.data.startswith("complete_"))
async def complete_order(callback: types.CallbackQuery):
    try: customer_id = int(callback.data.split("_")[1])
    except Exception:
        await callback.answer("Xato ID.", show_alert=True); return
    order = orders.get(customer_id)
    if not order: await callback.answer("Buyurtma topilmadi.", show_alert=True); return
    driver_id = order.get("driver_id")
    if callback.from_user.id != driver_id:
        await callback.answer("Faqat ushbu buyurtmani olgan haydovchi yakunlashi mumkin.", show_alert=True); return
    if order["status"] != "accepted":
        await callback.answer("Bu buyurtma yakunlab bo‘lmaydi (holat mos emas).", show_alert=True); return

    order["status"] = "completed"
    cancel_driver_reminders(customer_id)
    drv_msg_id = order.get("drv_info_msg_id")
    if drv_msg_id:
        try: await bot.edit_message_reply_markup(chat_id=driver_id, message_id=drv_msg_id, reply_markup=None)
        except Exception: pass
    chat_id = order.get("chat_id") or get_order_chat_id(order.get("region"))
    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=order["msg_id"], text=group_post_text(customer_id, order, status_note="✅ Holat: YAKUNLANDI"))
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=order["msg_id"], reply_markup=None)
    except Exception: pass

    cust_info_id = order.get("cust_info_msg_id")
    if cust_info_id:
        try: await bot.delete_message(chat_id=customer_id, message_id=cust_info_id)
        except Exception: pass
        order["cust_info_msg_id"] = None

    rating_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=str(i), callback_data=f"rate_{customer_id}_{i}") for i in range(1,6)]])
    try:
        rate_msg = await bot.send_message(customer_id, "✅ Buyurtmangiz muvaffaqiyatli yakunlandi.\nIltimos, xizmatimizni 1–5 baholang:", reply_markup=rating_kb)
        order["cust_rating_msg_id"] = rate_msg.message_id
    except Exception: pass
    await callback.answer("Buyurtma yakunlandi.")

@dp.callback_query(F.data.startswith("rate_"))
async def rate_order(callback: types.CallbackQuery):
    try: _, cust_id_str, score_str = callback.data.split("_"); customer_id = int(cust_id_str); score = int(score_str)
    except Exception:
        await callback.answer("Xato format.", show_alert=True); return
    order = orders.get(customer_id)
    if not order: await callback.answer("Buyurtma topilmadi.", show_alert=True); return
    if callback.from_user.id != customer_id:
        await callback.answer("Faqat buyurtma egasi baholay oladi.", show_alert=True); return
    if order.get("status") != "completed":
        await callback.answer("Baholash faqat yakunlangan buyurtma uchun.", show_alert=True); return

    order["rating"] = max(1, min(5, score))
    rate_msg_id = order.get("cust_rating_msg_id")
    if rate_msg_id:
        try: await bot.edit_message_reply_markup(chat_id=customer_id, message_id=rate_msg_id, reply_markup=None)
        except Exception: pass
    try: await bot.send_message(customer_id, f"😊 Rahmat! Bahoyingiz qabul qilindi: {order['rating']}/5.")
    except Exception: pass

    customer_name = user_profiles.get(customer_id, {}).get("name", "Mijoz")
    log_text = (f"📊 <a href=\"tg://user?id={customer_id}\">{customer_name}</a> mijoz sizning botingizni <b>{order['rating']}/5</b> ga baholadi.")
    try: await bot.send_message(RATINGS_CHAT_ID, log_text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception: pass
    await callback.answer("Rahmat!")

@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_order(callback: types.CallbackQuery):
    try: customer_id = int(callback.data.split("_")[1])
    except Exception:
        await callback.answer("Xato ID.", show_alert=True); return
    order = orders.get(customer_id)
    if not order:
        await callback.answer("Buyurtma topilmadi yoki allaqachon bekor qilingan.", show_alert=True); return
    if order.get("status") == "completed":
        await callback.answer("Bu buyurtma yakunlangan, bekor qilib bo‘lmaydi.", show_alert=True); return

    driver_id = order.get("driver_id"); caller = callback.from_user.id
    chat_id = order.get("chat_id") or get_order_chat_id(order.get("region"))

    # Mijoz bekor qildi
    if caller == customer_id:
        cancel_driver_reminders(customer_id)
        try: await bot.delete_message(chat_id=chat_id, message_id=order["msg_id"])
        except Exception: pass
        if driver_id:
            try: await bot.send_message(driver_id, "❌ Mijoz buyurtmani bekor qildi.")
            except Exception: pass
        try: await bot.send_message(customer_id, "❌ Buyurtmangiz bekor qilindi.")
        except Exception: pass
        orders.pop(customer_id, None)
        await callback.answer("Bekor qilindi (mijoz)."); return

    # Haydovchi bekor qildi
    if caller == driver_id:
        cancel_driver_reminders(customer_id)
        cust_info_id = order.get("cust_info_msg_id")
        if cust_info_id:
            try: await bot.delete_message(chat_id=customer_id, message_id=cust_info_id)
            except Exception: pass
            order["cust_info_msg_id"] = None
        try:
            await bot.send_message(customer_id, "❌ Buyurtmangiz haydovchi tomonidan bekor qilindi. Tez orada sizning buyurtmangizni yangi haydovchi qabul qiladi.")
        except Exception: pass
        reopen_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❗️ Qabul qilish", callback_data=f"accept_{customer_id}")]
        ])
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=order["msg_id"], text=group_post_text(customer_id, order, status_note=None))
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=order["msg_id"], reply_markup=reopen_kb)
        except Exception: pass
        drv_msg_id = order.get("drv_info_msg_id")
        if drv_msg_id:
            try: await bot.edit_message_reply_markup(chat_id=driver_id, message_id=drv_msg_id, reply_markup=None)
            except Exception: pass
        order["status"] = "open"; order["driver_id"] = None
        await callback.answer("Bekor qilindi (haydovchi)."); return

    # Admin bekor qildi
    if caller in ADMIN_IDS:
        cancel_driver_reminders(customer_id)
        try: await bot.delete_message(chat_id=chat_id, message_id=order["msg_id"])
        except Exception: pass
        if driver_id:
            try: await bot.send_message(driver_id, "❌ Buyurtma admin tomonidan bekor qilindi.")
            except Exception: pass
        try: await bot.send_message(customer_id, "❌ Buyurtmangiz admin tomonidan bekor qilindi.")
        except Exception: pass
        orders.pop(customer_id, None)
        await callback.answer("Bekor qilindi (admin)."); return

    await callback.answer("Bu buyurtmani bekor qilishga ruxsatingiz yo‘q.", show_alert=True)

# ================== DIAGNOSTIKA (ixtiyoriy) ==================
@dp.message(Command("test_payments"))
async def test_payments_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        await bot.send_message(PAYMENTS_CHAT_ID, "✅ Test: bot cheklar guruhiga xabar yubora oladi.")
        await message.reply("✅ OK: xabar cheklar guruhiga yuborildi.")
    except Exception as e:
        await message.reply(f"❌ Muvaffaqiyatsiz: {e}")

@dp.message(Command("test_payments_photo"))
async def test_payments_photo_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        url = "https://via.placeholder.com/600x240.png?text=Payments+Photo+Test"
        await bot.send_photo(PAYMENTS_CHAT_ID, url, caption="🧪 Test photo (payments)")
        await message.reply("✅ Rasm cheklar guruhiga yuborildi.")
    except Exception as e:
        await message.reply(f"❌ Rasm yuborilmadi: {e}")
        
# ================== ADMIN: FOYDALANUVCHILAR SONI ==================
@dp.message(Command("users_count"))
async def users_count_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    total = len(user_profiles or {})
    with_phone = sum(1 for _, p in (user_profiles or {}).items() if p.get("phone"))
    await message.reply(
        f"👥 Jami foydalanuvchilar: <b>{total}</b>\n"
        f"📞 Telefon saqlanganlar: <b>{with_phone}</b>",
        parse_mode="HTML"
    )

# ================== ADMIN: CSV EXPORT ==================
@dp.message(Command("export_users"))
async def export_users_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    rows = []
    for uid, prof in (user_profiles or {}).items():
        rows.append([uid, prof.get("name", ""), prof.get("phone", "")])

    # Fayl nomi (data/ ichida)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(DATA_DIR, f"users_{ts}.csv")

    # Excel uchun utf-8-sig
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id", "name", "phone"])
        writer.writerows(rows)

    try:
        await message.answer_document(
            document=FSInputFile(out_path),
            caption=f"👥 Foydalanuvchilar ro‘yxati (CSV) — {len(rows)} ta"
        )
    except Exception as e:
        await message.reply(f"❌ CSV yuborilmadi: {e}")

# ================== POLLING ==================
async def main():
    print("Bot ishga tushmoqda...")
    await bot.delete_webhook(drop_pending_updates=True)

    # >>> Trial nazoratchisini fon rejimda ishga tushiramiz
    asyncio.create_task(trial_watcher())

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
