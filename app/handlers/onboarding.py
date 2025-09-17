from __future__ import annotations

import asyncio
from datetime import datetime

from aiogram import F, types
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from ..bot_instance import bot, dp
from ..config import (
    ADMIN_IDS,
    BACK,
    CARD_HOLDER,
    CARD_NUMBER_DISPLAY,
    DRIVER_BTN,
    FREE_TRIAL_ENABLED,
    PAYMENTS_CHAT_ID,
    SUBSCRIPTION_PRICE,
)
from ..keyboards import (
    keyboard_with_back_cancel,
    order_keyboard,
    pickup_keyboard,
    share_phone_keyboard,
    vehicle_keyboard,
    when_keyboard,
)
from ..state import (
    drafts,
    driver_onboarding,
    subscriptions,
    trial_members,
    user_profiles,
)
from ..storage import save_users_to_disk
from ..trial import _send_trial_invite
from ..utils import human_dt, phone_display
from .orders import collect_flow


def _make_payment_kb(driver_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"payok_{driver_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"payno_{driver_id}"),
            ]
        ]
    )


async def _build_check_caption(uid: int, data: dict) -> str:
    name = data.get("name", "—")
    car_make = data.get("car_make", "—")
    car_plate = data.get("car_plate", "—")
    phone = data.get("phone", "—")
    caption = (
        "🧾 <b>Yangi obuna to‘lovi (haydovchi)</b>\n"
        f"👤 <b>F.I.Sh:</b> {name}\n"
        f"🚗 <b>Avtomobil:</b> {car_make}\n"
        f"🔢 <b>Raqam:</b> {car_plate}\n"
        f"📞 <b>Telefon:</b> {phone}\n"
        f"🔗 <b>Profil:</b> <a href=\"tg://user?id={uid}\">{uid}</a>\n\n"
        f"💳 <b>Miqdor:</b> {SUBSCRIPTION_PRICE:,} so‘m\n"
        "⚠️ <i>Ogohlantirish: soxtalashtirilgan chek yuborgan shaxsga nisbatan jinoyiy javobgarlik qo‘llanilishi mumkin.</i>"
    ).replace(",", " ")
    return caption


async def _send_check_to_payments(uid: int, caption: str, file_id: str, as_photo: bool) -> bool:
    keyboard = _make_payment_kb(uid)
    try:
        if as_photo:
            await bot.send_photo(
                chat_id=PAYMENTS_CHAT_ID,
                photo=file_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        else:
            await bot.send_document(
                chat_id=PAYMENTS_CHAT_ID,
                document=file_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        return True
    except Exception as exc:
        err = str(exc).lower()
        if as_photo and "not enough rights to send photos" in err:
            try:
                await bot.send_document(
                    chat_id=PAYMENTS_CHAT_ID,
                    document=file_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                return True
            except Exception as reexc:
                exc = reexc

        note = (
            "\n\n⚠️ Chekni cheklar guruhiga yuborib bo‘lmadi. Guruh ruxsatlarini tekshiring yoki bu xabarni oldinga yuboring."
        )
        for admin_id in ADMIN_IDS:
            try:
                if as_photo:
                    await bot.send_photo(admin_id, file_id, caption=caption + note, parse_mode="HTML")
                else:
                    await bot.send_document(admin_id, file_id, caption=caption + note, parse_mode="HTML")
            except Exception:
                pass
        warn = f"❗️ Chekni cheklar guruhiga yuborib bo‘lmadi.\nUser: {uid}\nXato: {exc}"
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, warn)
            except Exception:
                pass
        return False


@dp.callback_query(F.data == "driver_agree")
async def driver_agree_cb(callback: types.CallbackQuery) -> None:
    uid = callback.from_user.id
    driver_onboarding[uid] = {
        "stage": "name",
        "name": None,
        "car_make": None,
        "car_plate": None,
        "phone": None,
    }
    await callback.message.answer(
        "✍️ Iltimos, <b>Ism Familiya</b>ingizni yuboring:",
        parse_mode="HTML",
        reply_markup=keyboard_with_back_cancel([], show_back=True),
    )
    await callback.answer()


@dp.message(F.text == BACK)
async def back_flow(message: types.Message) -> None:
    uid = message.from_user.id

    if uid in driver_onboarding:
        stage = driver_onboarding[uid].get("stage")
        if stage == "name":
            driver_onboarding.pop(uid, None)
            await message.answer("Asosiy menyu", reply_markup=order_keyboard())
            return
        if stage == "car_make":
            driver_onboarding[uid]["stage"] = "name"
            await message.answer(
                "✍️ Iltimos, <b>Ism Familiya</b>ingizni yuboring:",
                parse_mode="HTML",
                reply_markup=keyboard_with_back_cancel([], show_back=True),
            )
            return
        if stage == "car_plate":
            driver_onboarding[uid]["stage"] = "car_make"
            await message.answer(
                "🚗 Avtomobil <b>markasi</b>ni yozing:",
                parse_mode="HTML",
                reply_markup=keyboard_with_back_cancel([], show_back=True),
            )
            return
        if stage == "phone":
            driver_onboarding[uid]["stage"] = "car_plate"
            await message.answer(
                "🔢 Avtomobil <b>davlat raqami</b>ni yozing:",
                parse_mode="HTML",
                reply_markup=keyboard_with_back_cancel([], show_back=True),
            )
            return
        if stage == "wait_check":
            await after_phone_collected(uid, message)
            return

    draft = drafts.get(uid)
    if not draft:
        await message.answer("Asosiy menyu", reply_markup=order_keyboard())
        return

    stage = draft["stage"]
    if stage == "vehicle":
        drafts.pop(uid, None)
        await message.answer("Asosiy menyu", reply_markup=order_keyboard())
        return
    if stage == "from":
        draft["stage"] = "vehicle"
        draft["vehicle"] = None
        await message.answer(
            "🚚 Qanday yuk mashinasi kerak?\nQuyidagidan tanlang yoki o‘zingiz yozing:",
            reply_markup=vehicle_keyboard(),
        )
        return
    if stage == "to":
        draft["stage"] = "from"
        draft["from"] = None
        await message.answer(
            "📍 Yuk **qayerdan** olinadi?\nManzilni yozing yoki “📍 Lokatsiyani yuborish” tugmasi:",
            reply_markup=pickup_keyboard(),
        )
        return
    if stage == "when_select":
        draft["stage"] = "to"
        draft["when"] = None
        await message.answer(
            "📦 Yuk **qayerga** yetkaziladi? Manzilni yozing:",
            reply_markup=keyboard_with_back_cancel([], show_back=True),
        )
        return
    if stage == "when_input":
        draft["stage"] = "when_select"
        await message.answer(
            "🕒 Qaysi **vaqtga** kerak?\nTugmalardan tanlang yoki `HH:MM` yozing.",
            reply_markup=when_keyboard(),
        )
        return


@dp.message(F.text)
async def onboarding_or_order_text(message: types.Message) -> None:
    uid = message.from_user.id
    text = (message.text or "").strip()

    if text == BACK:
        await back_flow(message)
        return

    if uid in driver_onboarding:
        stage = driver_onboarding[uid].get("stage")

        if stage == "name":
            driver_onboarding[uid]["name"] = text
            driver_onboarding[uid]["stage"] = "car_make"
            await message.answer(
                "🚗 Avtomobil <b>markasi</b>ni yozing (masalan: Labo / Porter / Isuzu):",
                parse_mode="HTML",
                reply_markup=keyboard_with_back_cancel([], show_back=True),
            )
            return

        if stage == "car_make":
            driver_onboarding[uid]["car_make"] = text
            driver_onboarding[uid]["stage"] = "car_plate"
            await message.answer(
                "🔢 Avtomobil <b>davlat raqami</b>ni yozing (masalan: 01A123BC):",
                parse_mode="HTML",
                reply_markup=keyboard_with_back_cancel([], show_back=True),
            )
            return

        if stage == "car_plate":
            driver_onboarding[uid]["car_plate"] = text
            driver_onboarding[uid]["stage"] = "phone"
            profile_phone = user_profiles.get(uid, {}).get("phone")
            hint = (
                f"\n\nBizdagi saqlangan raqam: <b>{phone_display(profile_phone)}</b>"
                if profile_phone
                else ""
            )
            await message.answer(
                "📞 Kontakt raqamingizni yuboring.\nRaqamni yozishingiz yoki pastdagi tugma orqali ulashishingiz mumkin."
                + hint,
                parse_mode="HTML",
                reply_markup=share_phone_keyboard(),
            )
            return

        if stage == "phone":
            phone = text
            driver_onboarding[uid]["phone"] = phone if phone.startswith("+") else f"+{phone}"
            await after_phone_collected(uid, message)
            return

        return

    await collect_flow(message)


async def after_phone_collected(uid: int, message: types.Message) -> None:
    data = driver_onboarding.get(uid, {})
    name = data.get("name", "—")
    car_make = data.get("car_make", "—")
    car_plate = data.get("car_plate", "—")
    phone = data.get("phone", "—")

    if uid in user_profiles:
        user_profiles[uid]["phone"] = phone if phone and phone != "—" else user_profiles[uid].get("phone")
        user_profiles[uid]["name"] = user_profiles[uid].get("name") or name
    else:
        user_profiles[uid] = {"name": name, "phone": phone}

    await save_users_to_disk(user_profiles)

    profile = user_profiles.get(uid, {})
    trial_granted_at = profile.get("trial_granted_at")
    trial_joined_at = profile.get("trial_joined_at")

    if FREE_TRIAL_ENABLED and not subscriptions.get(uid, {}).get("active"):
        if not trial_granted_at:
            try:
                await message.answer(
                    "🎁 Siz uchun <b>30 kunlik bepul sinov</b> ishga tushiriladi.\n"
                    "Bir zumda havolani yuboraman...",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            await _send_trial_invite(uid)
            driver_onboarding.pop(uid, None)
            return
        else:
            dt_txt = human_dt(trial_joined_at or trial_granted_at)
            try:
                await message.answer(
                    f"ℹ️ Siz {dt_txt} sanada 30 kunlik bepul sinov orqali haydovchilar guruhiga qo‘shilgansiz."
                    " Bepul sinov faqat bir martalik, shuning uchun qayta havola yuborilmaydi.",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    price_txt = f"{SUBSCRIPTION_PRICE:,}".replace(",", " ")
    pay_text = (
        f"💳 <b>Obuna to‘lovi:</b> <code>{price_txt} so‘m</code> (1 oy)\n"
        f"🧾 <b>Karta:</b> <code>{CARD_NUMBER_DISPLAY}</code>\n"
        f"👤 Karta egasi: <b>{CARD_HOLDER}</b>\n\n"
        "✅ To‘lovni amalga oshirgach, <b>chek rasm</b>ini yuboring (screenshot ham bo‘ladi).\n"
        "⚠️ <b>Ogohlantirish:</b> soxtalashtirilgan chek yuborgan shaxsga <b>jinoyiy javobgarlik</b> qo‘llanilishi mumkin."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Karta raqamini nusxalash",
                    callback_data="copy_card",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📤 Chekni yuborish",
                    callback_data="send_check",
                )
            ],
        ]
    )

    await message.answer(
        "Ma’lumotlaringiz qabul qilindi ✅\n\n"
        f"👤 <b>F.I.Sh:</b> {name}\n"
        f"🚗 <b>Avtomobil:</b> {car_make}\n"
        f"🔢 <b>Raqam:</b> {car_plate}\n"
        f"📞 <b>Telefon:</b> {phone_display(user_profiles.get(uid, {}).get('phone', phone))}",
        parse_mode="HTML",
    )
    await message.answer(pay_text, parse_mode="HTML", reply_markup=keyboard)
    driver_onboarding[uid]["stage"] = "wait_check"


@dp.callback_query(F.data == "send_check")
async def send_check_cb(callback: types.CallbackQuery) -> None:
    uid = callback.from_user.id
    if uid not in driver_onboarding:
        await callback.answer()
        return
    driver_onboarding[uid]["stage"] = "wait_check"
    await callback.message.answer(
        "📸 Iltimos, <b>chek rasmini</b> bitta rasm ko‘rinishida yuboring (screenshot ham bo‘ladi).",
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "copy_card")
async def copy_card_cb(callback: types.CallbackQuery) -> None:
    try:
        await callback.answer("Karta raqami xabar sifatida yuborildi", show_alert=True)
    except Exception:
        pass
    try:
        await callback.message.answer(
            f"💳 Karta raqami: <code>{CARD_NUMBER_DISPLAY}</code>", parse_mode="HTML"
        )
    except Exception:
        pass


@dp.message(F.photo)
async def receive_check_photo(message: types.Message) -> None:
    uid = message.from_user.id
    if uid not in driver_onboarding or driver_onboarding[uid].get("stage") != "wait_check":
        return
    data = driver_onboarding.get(uid, {})
    file_id = message.photo[-1].file_id
    caption = await _build_check_caption(uid, data)
    ok = await _send_check_to_payments(uid, caption, file_id, as_photo=True)
    if not ok:
        await message.answer(
            "❌ Chekni log guruhiga yuborishda xatolik. Iltimos, keyinroq qayta urinib ko‘ring yoki admin bilan bog‘laning."
        )
        return
    await message.answer(
        "✅ Chek yuborildi. Iltimos, <b>tasdiqlashni kuting</b>.\n"
        "Tasdiqlangandan so‘ng <b>admin sizga Haydovchilar guruhi</b> silkasini yuboradi.",
        parse_mode="HTML",
        reply_markup=order_keyboard(),
    )
    driver_onboarding.pop(uid, None)


@dp.message(F.document)
async def receive_check_document(message: types.Message) -> None:
    uid = message.from_user.id
    if uid not in driver_onboarding or driver_onboarding[uid].get("stage") != "wait_check":
        return
    doc = message.document
    file_id = doc.file_id
    data = driver_onboarding.get(uid, {})
    caption = await _build_check_caption(uid, data)
    ok = await _send_check_to_payments(uid, caption, file_id, as_photo=False)
    if not ok:
        await message.answer(
            "❌ Chekni log guruhiga yuborishda xatolik. Iltimos, keyinroq qayta urinib ko‘ring yoki admin bilan bog‘laning."
        )
        return
    await message.answer(
        "✅ Chek yuborildi. Iltimos, <b>tasdiqlashni kuting</b>.\n"
        "Tasdiqlangandan so‘ng <b>admin sizga Haydovchilar guruhi</b> silkasini yuboradi.",
        parse_mode="HTML",
        reply_markup=order_keyboard(),
    )
    driver_onboarding.pop(uid, None)


__all__ = [
    "after_phone_collected",
    "back_flow",
]
