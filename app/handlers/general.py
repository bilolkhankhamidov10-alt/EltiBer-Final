from __future__ import annotations

import os

from aiogram import F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from ..bot_instance import dp
from ..config import (
    CANCEL,
    CONTACT_BTN,
    CONTACT_IMAGE_PATH,
    CONTACT_IMAGE_URL,
    CONTACT_PHONE,
    CONTACT_PHONE_LINK,
    CONTACT_TG,
    DRIVER_BTN,
    ESLATMA_IMAGE_PATH,
)
from ..keyboards import contact_keyboard, order_keyboard
from ..state import drafts, driver_onboarding, user_profiles
from ..storage import save_users_to_disk
from .onboarding import after_phone_collected
from .orders import prompt_order_flow


@dp.message(CommandStart())
async def start_command(message: types.Message) -> None:
    uid = message.from_user.id
    profile = user_profiles.get(uid)

    if not profile or not profile.get("phone"):
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="📞 Telefon raqamingizni yuboring", request_contact=True)]],
            resize_keyboard=True,
        )
        await message.answer(
            f"Salom, {message.from_user.full_name}! 👋\n"
            "Iltimos, bir marta telefon raqamingizni yuboring:",
            reply_markup=keyboard,
        )
    else:
        await message.answer("Quyidagi menyudan tanlang 👇", reply_markup=order_keyboard())


@dp.message(F.contact)
async def contact_received(message: types.Message) -> None:
    uid = message.from_user.id
    raw_phone = message.contact.phone_number or ""
    phone = raw_phone if raw_phone.startswith("+") else f"+{raw_phone}"

    profile = user_profiles.get(uid, {})
    profile.update({"name": message.from_user.full_name, "phone": phone})
    user_profiles[uid] = profile
    await save_users_to_disk(user_profiles)

    if uid in driver_onboarding and driver_onboarding[uid].get("stage") == "phone":
        driver_onboarding[uid]["phone"] = phone
        await after_phone_collected(uid, message)
        return

    await message.answer("✅ Telefon raqamingiz saqlandi.", reply_markup=types.ReplyKeyboardRemove())
    await message.answer("Endi quyidagi menyudan tanlang 👇", reply_markup=order_keyboard())


@dp.message(F.text == CONTACT_BTN)
async def contact_us(message: types.Message) -> None:
    caption = (
        "<b>📞 Biz bilan bog'lanish</b>\n\n"
        f"• Telefon: <a href=\"tel:{CONTACT_PHONE_LINK}\">{CONTACT_PHONE}</a>\n"
        f"• Telegram: @{CONTACT_TG}"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✉️ Telegramga yozish", url=f"https://t.me/{CONTACT_TG}"
                )
            ]
        ]
    )

    sent = False
    if CONTACT_IMAGE_PATH and os.path.exists(CONTACT_IMAGE_PATH):
        try:
            await message.answer_photo(
                photo=FSInputFile(CONTACT_IMAGE_PATH),
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            sent = True
        except Exception:
            sent = False

    if not sent and CONTACT_IMAGE_URL:
        try:
            await message.answer_photo(
                photo=CONTACT_IMAGE_URL,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            sent = True
        except Exception:
            sent = False

    if not sent:
        await message.answer(caption, parse_mode="HTML", reply_markup=keyboard)


@dp.message(Command("buyurtma"))
async def buyurtma_cmd(message: types.Message) -> None:
    await prompt_order_flow(message)


@dp.message(F.text == "🚖 Buyurtma berish")
async def buyurtma_btn(message: types.Message) -> None:
    await prompt_order_flow(message)


@dp.message(F.text == CANCEL)
async def cancel_flow(message: types.Message) -> None:
    uid = message.from_user.id
    drafts.pop(uid, None)
    driver_onboarding.pop(uid, None)
    await message.answer("❌ Bekor qilindi.", reply_markup=order_keyboard())


@dp.message(F.text == DRIVER_BTN)
async def haydovchi_bolish(message: types.Message) -> None:
    uid = message.from_user.id
    drafts.pop(uid, None)
    driver_onboarding.pop(uid, None)

    if ESLATMA_IMAGE_PATH and os.path.exists(ESLATMA_IMAGE_PATH):
        try:
            await message.answer_photo(
                photo=FSInputFile(ESLATMA_IMAGE_PATH),
                caption="🔔 <b>ESLATMA</b>",
                parse_mode="HTML",
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
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Shartlarga roziman", callback_data="driver_agree")]]
    )
    await message.answer(req_text, parse_mode="HTML", reply_markup=keyboard)
