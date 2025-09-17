from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from aiogram import F, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..bot_instance import bot, dp
from ..config import ADMIN_IDS, BOSHQA, DRIVERS_CHAT_ID, HOZIR, RATINGS_CHAT_ID
from ..keyboards import (
    contact_keyboard,
    keyboard_with_back_cancel,
    order_keyboard,
    pickup_keyboard,
    vehicle_keyboard,
    when_keyboard,
)
from ..state import drafts, orders, user_profiles
from ..utils import event_dt_today_or_now, is_hhmm, normalize_hhmm, phone_display


async def prompt_order_flow(message: types.Message) -> None:
    uid = message.from_user.id
    profile = user_profiles.get(uid)

    if not profile or not profile.get("phone"):
        await message.answer("Iltimos, telefon raqamingizni yuboring 📞", reply_markup=contact_keyboard())
        return

    drafts[uid] = {"stage": "vehicle", "vehicle": None, "from": None, "to": None, "when": None}
    await message.answer(
        "🚚 Qanday yuk mashinasi kerak?\nQuyidagidan tanlang yoki o‘zingiz yozing:",
        reply_markup=vehicle_keyboard(),
    )


@dp.message(F.location)
async def location_received(message: types.Message) -> None:
    uid = message.from_user.id
    if uid not in drafts:
        return
    draft = drafts[uid]
    if draft.get("stage") != "from":
        return
    lat = message.location.latitude
    lon = message.location.longitude
    draft["from"] = f"https://maps.google.com/?q={lat},{lon}"
    draft["stage"] = "to"
    await message.answer(
        "✅ Lokatsiya qabul qilindi.\n\n📦 Endi yuk **qayerga** yetkaziladi? Manzilni yozing:",
        reply_markup=keyboard_with_back_cancel([], show_back=True),
    )


async def collect_flow(message: types.Message) -> None:
    uid = message.from_user.id
    if uid not in drafts:
        return

    draft = drafts[uid]
    stage = draft["stage"]
    text = (message.text or "").strip()

    if stage == "vehicle":
        draft["vehicle"] = text if text else "Noma'lum"
        draft["stage"] = "from"
        await message.answer(
            "📍 Yuk **qayerdan** olinadi?\nManzilni yozing yoki “📍 Lokatsiyani yuborish”:",
            reply_markup=pickup_keyboard(),
        )
        return

    if stage == "from":
        draft["from"] = text
        draft["stage"] = "to"
        await message.answer(
            "📦 Yuk **qayerga** yetkaziladi? Manzilni yozing:",
            reply_markup=keyboard_with_back_cancel([], show_back=True),
        )
        return

    if stage == "to":
        draft["to"] = text
        draft["stage"] = "when_select"
        await message.answer(
            "🕒 Qaysi **vaqtga** kerak?\nTugmalardan tanlang yoki `HH:MM` yozing.",
            reply_markup=when_keyboard(),
        )
        return

    if stage == "when_select":
        if text == HOZIR:
            draft["when"] = datetime.now().strftime("%H:%M")
            await finalize_and_send(message, draft)
            return
        if text == BOSHQA:
            draft["stage"] = "when_input"
            await message.answer(
                "⏰ Vaqtni kiriting (`HH:MM`, masalan: `19:00`):",
                reply_markup=keyboard_with_back_cancel([], show_back=True),
            )
            return
        if is_hhmm(text):
            draft["when"] = normalize_hhmm(text)
            await finalize_and_send(message, draft)
            return
        await message.answer(
            "❗️ Vaqt formati `HH:MM` bo‘lishi kerak. Yoki tugmalarni tanlang.",
            reply_markup=when_keyboard(),
        )
        return

    if stage == "when_input":
        if is_hhmm(text):
            draft["when"] = normalize_hhmm(text)
            await finalize_and_send(message, draft)
            return
        await message.answer(
            "❗️ Noto‘g‘ri format. `HH:MM` yozing (masalan: `19:00`).",
            reply_markup=keyboard_with_back_cancel([], show_back=True),
        )


def group_post_text(customer_id: int, order_data: dict, status_note: str | None = None) -> str:
    customer_name = user_profiles.get(customer_id, {}).get("name", "Mijoz")
    base = (
        f"📦 Yangi buyurtma!\n"
        f"👤 Mijoz: {customer_name}\n"
        f"🚚 Mashina: {order_data['vehicle']}\n"
        f"➡️ Yo‘nalish:\n"
        f"   • Qayerdan: {order_data['from']}\n"
        f"   • Qayerga: {order_data['to']}\n"
        f"🕒 Vaqt: {order_data['when']}\n"
        f"ℹ️ Telefon raqami guruhda ko‘rsatilmaydi."
    )
    if status_note:
        base += f"\n{status_note}"
    return base


async def finalize_and_send(message: types.Message, draft: dict) -> None:
    uid = message.from_user.id
    order_payload = {
        "vehicle": draft["vehicle"],
        "from": draft["from"],
        "to": draft["to"],
        "when": draft["when"],
    }

    keyboard_group = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❗️ Qabul qilish", callback_data=f"accept_{uid}")]]
    )
    sent = await bot.send_message(
        DRIVERS_CHAT_ID,
        group_post_text(uid, order_payload),
        reply_markup=keyboard_group,
    )

    orders[uid] = {
        **order_payload,
        "msg_id": sent.message_id,
        "status": "open",
        "driver_id": None,
        "cust_info_msg_id": None,
        "drv_info_msg_id": None,
        "cust_rating_msg_id": None,
        "rating": None,
        "reminder_tasks": [],
    }

    keyboard_customer = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Buyurtmani bekor qilish", callback_data=f"cancel_{uid}")]]
    )
    await message.answer(
        "✅ Buyurtma haydovchilarga yuborildi.\nKerak bo‘lsa bekor qilishingiz mumkin.",
        reply_markup=keyboard_customer,
    )
    await message.answer("Asosiy menyu", reply_markup=order_keyboard())
    drafts.pop(uid, None)


def cancel_driver_reminders(customer_id: int) -> None:
    order_info = orders.get(customer_id)
    if not order_info:
        return
    tasks = order_info.get("reminder_tasks") or []
    for task in tasks:
        try:
            task.cancel()
        except Exception:
            pass
    order_info["reminder_tasks"] = []


async def _sleep_and_notify(delay: float, chat_id: int, text: str) -> None:
    try:
        if delay > 0:
            await asyncio.sleep(delay)
        await bot.send_message(chat_id, text, disable_web_page_preview=True)
    except asyncio.CancelledError:
        return
    except Exception:
        pass


def schedule_driver_reminders(customer_id: int) -> None:
    order_info = orders.get(customer_id)
    if not order_info or order_info.get("status") != "accepted":
        return

    driver_id = order_info.get("driver_id")
    if not driver_id:
        return

    cancel_driver_reminders(customer_id)
    now = datetime.now()
    event_dt = event_dt_today_or_now(order_info["when"], now=now)
    seconds_to_event = (event_dt - now).total_seconds()
    milestones = [
        (3600, "⏳ 1 soat qoldi"),
        (1800, "⏳ 30 daqiqa qoldi"),
        (900, "⏳ 15 daqiqa qoldi"),
        (0, "⏰ Vaqti bo‘ldi"),
    ]
    base = (
        f"{order_info['when']} vaqti uchun buyurtma.\n"
        f"Yo‘nalish: {order_info['from']} → {order_info['to']}\n"
        "Muvofiqlashtirishni unutmang."
    )
    order_info["reminder_tasks"] = []
    for offset, label in milestones:
        delay = seconds_to_event - offset
        if delay < 0:
            continue
        text = f"{label} — {base}"
        task = asyncio.create_task(_sleep_and_notify(delay, driver_id, text))
        order_info.setdefault("reminder_tasks", []).append(task)


@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: types.CallbackQuery) -> None:
    try:
        customer_id = int(callback.data.split("_")[1])
    except Exception:
        await callback.answer("Xato ID.", show_alert=True)
        return

    order_info = orders.get(customer_id)
    customer_profile = user_profiles.get(customer_id)
    if not order_info or not customer_profile:
        await callback.answer("Bu buyurtma topilmadi yoki allaqachon yakunlangan.", show_alert=True)
        return

    if order_info.get("status") != "open":
        await callback.answer("Bu buyurtma allaqachon qabul qilingan yoki yakunlangan.", show_alert=True)
        return

    driver_id = callback.from_user.id
    driver_profile = user_profiles.get(driver_id)
    if not driver_profile or not driver_profile.get("phone"):
        await bot.send_message(
            driver_id,
            "ℹ️ Buyurtmani qabul qilishdan oldin telefon raqamingizni yuboring.",
            reply_markup=contact_keyboard(),
        )
        await callback.answer("Avval telefon raqamingizni yuboring.", show_alert=True)
        return

    order_info["status"] = "accepted"
    order_info["driver_id"] = driver_id

    customer_name = customer_profile.get("name", "Noma'lum")
    customer_phone = customer_profile.get("phone", "—")
    driver_name = driver_profile.get("name", callback.from_user.full_name)
    driver_phone = driver_profile.get("phone", "—")

    driver_text = (
        f"✅ Buyurtma sizga biriktirildi\n\n"
        f"👤 Mijoz: {customer_name}\n"
        f"📞 Telefon: <a href=\"tg://user?id={customer_id}\">{phone_display(customer_phone)}</a>\n"
        f"🚚 Mashina: {order_info['vehicle']}\n"
        f"➡️ Yo‘nalish:\n   • Qayerdan: {order_info['from']}\n"
        f"   • Qayerga: {order_info['to']}\n"
        f"🕒 Vaqt: {order_info['when']}"
    )
    driver_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Buyurtmani yakunlash", callback_data=f"complete_{customer_id}")],
            [InlineKeyboardButton(text="❌ Buyurtmani bekor qilish", callback_data=f"cancel_{customer_id}")],
            [InlineKeyboardButton(text="👤 Mijoz profili", url=f"tg://user?id={customer_id}")],
        ]
    )
    try:
        driver_msg = await bot.send_message(
            driver_id,
            driver_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=driver_keyboard,
        )
        order_info["drv_info_msg_id"] = driver_msg.message_id
    except Exception:
        await callback.answer("Haydovchiga DM yuborilmadi. Botga /start yozing.", show_alert=True)
        return

    try:
        await bot.edit_message_text(
            chat_id=DRIVERS_CHAT_ID,
            message_id=order_info["msg_id"],
            text=group_post_text(customer_id, order_info, status_note="✅ Holat: QABUL QILINDI"),
        )
        await bot.edit_message_reply_markup(
            chat_id=DRIVERS_CHAT_ID,
            message_id=order_info["msg_id"],
            reply_markup=None,
        )
    except Exception:
        pass

    customer_text = (
        f"🚚 Buyurtmangizni haydovchi qabul qildi.\n\n"
        f"👨‍✈️ Haydovchi: {driver_name}\n"
        f"📞 Telefon: <a href=\"tg://user?id={driver_id}\">{phone_display(driver_phone)}</a>"
    )
    customer_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Buyurtmani bekor qilish", callback_data=f"cancel_{customer_id}")],
            [InlineKeyboardButton(text="👨‍✈️ Haydovchi profili", url=f"tg://user?id={driver_id}")],
        ]
    )
    try:
        cust_msg = await bot.send_message(
            customer_id,
            customer_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=customer_keyboard,
        )
        order_info["cust_info_msg_id"] = cust_msg.message_id
    except Exception:
        pass

    schedule_driver_reminders(customer_id)
    await callback.answer("Buyurtma sizga biriktirildi!")


@dp.callback_query(F.data.startswith("complete_"))
async def complete_order(callback: types.CallbackQuery) -> None:
    try:
        customer_id = int(callback.data.split("_")[1])
    except Exception:
        await callback.answer("Xato ID.", show_alert=True)
        return

    order_info = orders.get(customer_id)
    if not order_info:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return

    driver_id = order_info.get("driver_id")
    if callback.from_user.id != driver_id:
        await callback.answer(
            "Faqat ushbu buyurtmani olgan haydovchi yakunlashi mumkin.", show_alert=True
        )
        return

    if order_info.get("status") != "accepted":
        await callback.answer("Bu buyurtma yakunlab bo‘lmaydi (holat mos emas).", show_alert=True)
        return

    order_info["status"] = "completed"
    cancel_driver_reminders(customer_id)

    driver_msg_id = order_info.get("drv_info_msg_id")
    if driver_msg_id:
        try:
            await bot.edit_message_reply_markup(chat_id=driver_id, message_id=driver_msg_id, reply_markup=None)
        except Exception:
            pass

    try:
        await bot.edit_message_text(
            chat_id=DRIVERS_CHAT_ID,
            message_id=order_info["msg_id"],
            text=group_post_text(customer_id, order_info, status_note="✅ Holat: YAKUNLANDI"),
        )
        await bot.edit_message_reply_markup(
            chat_id=DRIVERS_CHAT_ID,
            message_id=order_info["msg_id"],
            reply_markup=None,
        )
    except Exception:
        pass

    cust_info_id = order_info.get("cust_info_msg_id")
    if cust_info_id:
        try:
            await bot.delete_message(chat_id=customer_id, message_id=cust_info_id)
        except Exception:
            pass
        order_info["cust_info_msg_id"] = None

    rating_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=str(score), callback_data=f"rate_{customer_id}_{score}") for score in range(1, 6)]
        ]
    )
    try:
        rating_msg = await bot.send_message(
            customer_id,
            "✅ Buyurtmangiz muvaffaqiyatli yakunlandi.\nIltimos, xizmatimizni 1–5 baholang:",
            reply_markup=rating_keyboard,
        )
        order_info["cust_rating_msg_id"] = rating_msg.message_id
    except Exception:
        pass

    await callback.answer("Buyurtma yakunlandi.")


@dp.callback_query(F.data.startswith("rate_"))
async def rate_order(callback: types.CallbackQuery) -> None:
    try:
        _, cust_id_str, score_str = callback.data.split("_")
        customer_id = int(cust_id_str)
        score = int(score_str)
    except Exception:
        await callback.answer("Xato format.", show_alert=True)
        return

    order_info = orders.get(customer_id)
    if not order_info:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return

    if callback.from_user.id != customer_id:
        await callback.answer("Faqat buyurtma egasi baholay oladi.", show_alert=True)
        return

    if order_info.get("status") != "completed":
        await callback.answer("Baholash faqat yakunlangan buyurtma uchun.", show_alert=True)
        return

    order_info["rating"] = max(1, min(5, score))
    rate_msg_id = order_info.get("cust_rating_msg_id")
    if rate_msg_id:
        try:
            await bot.edit_message_reply_markup(
                chat_id=customer_id,
                message_id=rate_msg_id,
                reply_markup=None,
            )
        except Exception:
            pass
    try:
        await bot.send_message(
            customer_id, f"😊 Rahmat! Bahoyingiz qabul qilindi: {order_info['rating']}/5."
        )
    except Exception:
        pass

    customer_name = user_profiles.get(customer_id, {}).get("name", "Mijoz")
    log_text = (
        f"📊 <a href=\"tg://user?id={customer_id}\">{customer_name}</a> mijoz sizning botingizni <b>{order_info['rating']}/5</b> ga baholadi."
    )
    try:
        await bot.send_message(
            RATINGS_CHAT_ID,
            log_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        pass

    await callback.answer("Rahmat!")


@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_order(callback: types.CallbackQuery) -> None:
    try:
        customer_id = int(callback.data.split("_")[1])
    except Exception:
        await callback.answer("Xato ID.", show_alert=True)
        return

    order_info = orders.get(customer_id)
    if not order_info:
        await callback.answer("Buyurtma topilmadi yoki allaqachon bekor qilingan.", show_alert=True)
        return

    if order_info.get("status") == "completed":
        await callback.answer("Bu buyurtma yakunlangan, bekor qilib bo‘lmaydi.", show_alert=True)
        return

    driver_id = order_info.get("driver_id")
    caller_id = callback.from_user.id

    if caller_id == customer_id:
        cancel_driver_reminders(customer_id)
        try:
            await bot.delete_message(chat_id=DRIVERS_CHAT_ID, message_id=order_info["msg_id"])
        except Exception:
            pass
        if driver_id:
            try:
                await bot.send_message(driver_id, "❌ Mijoz buyurtmani bekor qildi.")
            except Exception:
                pass
        try:
            await bot.send_message(customer_id, "❌ Buyurtmangiz bekor qilindi.")
        except Exception:
            pass
        orders.pop(customer_id, None)
        await callback.answer("Bekor qilindi (mijoz).")
        return

    if caller_id == driver_id:
        cancel_driver_reminders(customer_id)
        cust_msg_id = order_info.get("cust_info_msg_id")
        if cust_msg_id:
            try:
                await bot.delete_message(chat_id=customer_id, message_id=cust_msg_id)
            except Exception:
                pass
            order_info["cust_info_msg_id"] = None
        try:
            await bot.send_message(
                customer_id,
                "❌ Buyurtmangiz haydovchi tomonidan bekor qilindi. Tez orada sizning buyurtmangizni yangi haydovchi qabul qiladi.",
            )
        except Exception:
            pass
        reopen_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❗️ Qabul qilish", callback_data=f"accept_{customer_id}")]]
        )
        try:
            await bot.edit_message_text(
                chat_id=DRIVERS_CHAT_ID,
                message_id=order_info["msg_id"],
                text=group_post_text(customer_id, order_info, status_note=None),
            )
            await bot.edit_message_reply_markup(
                chat_id=DRIVERS_CHAT_ID,
                message_id=order_info["msg_id"],
                reply_markup=reopen_keyboard,
            )
        except Exception:
            pass
        driver_msg_id = order_info.get("drv_info_msg_id")
        if driver_msg_id:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=driver_id,
                    message_id=driver_msg_id,
                    reply_markup=None,
                )
            except Exception:
                pass
        order_info["status"] = "open"
        order_info["driver_id"] = None
        await callback.answer("Bekor qilindi (haydovchi).")
        return

    if caller_id in ADMIN_IDS:
        cancel_driver_reminders(customer_id)
        try:
            await bot.delete_message(chat_id=DRIVERS_CHAT_ID, message_id=order_info["msg_id"])
        except Exception:
            pass
        if driver_id:
            try:
                await bot.send_message(driver_id, "❌ Buyurtma admin tomonidan bekor qilindi.")
            except Exception:
                pass
        try:
            await bot.send_message(customer_id, "❌ Buyurtmangiz admin tomonidan bekor qilindi.")
        except Exception:
            pass
        orders.pop(customer_id, None)
        await callback.answer("Bekor qilindi (admin).")
        return

    await callback.answer("Bu buyurtmani bekor qilishga ruxsatingiz yo‘q.", show_alert=True)


__all__ = [
    "prompt_order_flow",
    "collect_flow",
    "schedule_driver_reminders",
    "cancel_driver_reminders",
]
