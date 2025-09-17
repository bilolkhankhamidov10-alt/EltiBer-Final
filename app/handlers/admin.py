from __future__ import annotations

import csv
import os
from datetime import datetime

from aiogram import types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from ..bot_instance import bot, dp
from ..config import (
    ADMIN_IDS,
    CARD_HOLDER,
    CARD_NUMBER_DISPLAY,
    DATA_DIR,
    DRIVERS_CHAT_ID,
    PAYMENTS_CHAT_ID,
    SUBSCRIPTION_PRICE,
)
from ..state import pending_invites, subscriptions, trial_members, user_profiles


async def _send_driver_invite_and_mark(callback: types.CallbackQuery, driver_id: int) -> None:
    try:
        invite = await bot.create_chat_invite_link(
            chat_id=DRIVERS_CHAT_ID,
            name=f"driver-{driver_id}",
            member_limit=1,
        )
        invite_link = invite.invite_link
    except Exception as exc:
        await callback.answer(f"❌ Silka yaratilmedi: {exc}", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="👥 Haydovchilar guruhiga qo‘shilish", url=invite_link)]]
    )
    try:
        dm = await bot.send_message(
            chat_id=driver_id,
            text=(
                "✅ <b>To‘lov tasdiqlandi.</b>\n\n"
                "Quyidagi tugma orqali <b>Haydovchilar guruhiga</b> qo‘shiling. "
                "Guruhga qo‘shilgandan so‘ng bu xabar avtomatik o‘chiriladi."
            ),
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        pending_invites[driver_id] = {"msg_id": dm.message_id, "link": invite_link}
        subscriptions[driver_id] = {"active": True}
        trial_members.pop(driver_id, None)
    except Exception:
        await callback.answer("❌ Haydovchiga DM yuborilmadi (botga /start yozmagan bo‘lishi mumkin).", show_alert=True)
        return

    try:
        original_caption = callback.message.caption or ""
        admin_name = callback.from_user.username or callback.from_user.full_name
        new_caption = (
            f"{original_caption}\n\n✅ <b>Tasdiqlandi</b> — {admin_name} • {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        await bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=new_caption,
            parse_mode="HTML",
            reply_markup=None,
        )
    except Exception:
        try:
            await bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                reply_markup=None,
            )
        except Exception:
            pass

    await callback.answer("✅ Tasdiqlandi va silka yuborildi.")


@dp.callback_query(lambda c: c.data and c.data.startswith("payok_"))
async def cb_payment_ok(callback: types.CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Faqat admin tasdiqlashi mumkin.", show_alert=True)
        return
    try:
        driver_id = int(callback.data.split("_")[1])
    except Exception:
        await callback.answer("Xato ID.", show_alert=True)
        return

    await _send_driver_invite_and_mark(callback, driver_id)


@dp.callback_query(lambda c: c.data and c.data.startswith("payno_"))
async def cb_payment_no(callback: types.CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Faqat admin rad etishi mumkin.", show_alert=True)
        return
    try:
        driver_id = int(callback.data.split("_")[1])
    except Exception:
        await callback.answer("Xato ID.", show_alert=True)
        return

    try:
        await bot.send_message(
            driver_id,
            "❌ To‘lovingiz <b>rad etildi</b>.\n"
            "Iltimos, to‘g‘ri va aniq chek rasmini qaytadan yuboring.",
            parse_mode="HTML",
        )
    except Exception:
        pass

    try:
        original_caption = callback.message.caption or ""
        admin_name = callback.from_user.username or callback.from_user.full_name
        new_caption = (
            f"{original_caption}\n\n❌ <b>Rad etildi</b> — {admin_name} • {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        await bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=new_caption,
            parse_mode="HTML",
            reply_markup=None,
        )
    except Exception:
        try:
            await bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                reply_markup=None,
            )
        except Exception:
            pass

    await callback.answer("Rad etildi.")


@dp.message(Command("tasdiq"))
async def admin_confirm_payment(message: types.Message) -> None:
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS:
        return

    parts = (message.text or "").strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.reply("Foydalanish: <code>/tasdiq USER_ID</code>", parse_mode="HTML")
        return

    driver_id = int(parts[1])

    try:
        invite = await bot.create_chat_invite_link(
            chat_id=DRIVERS_CHAT_ID,
            name=f"driver-{driver_id}",
            member_limit=1,
        )
        invite_link = invite.invite_link
    except Exception:
        await message.reply("❌ Taklif havolasini yaratib bo‘lmadi. Bot guruhda admin ekanini tekshiring.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="👥 Haydovchilar guruhiga qo‘shilish", url=invite_link)]]
    )
    try:
        dm = await bot.send_message(
            chat_id=driver_id,
            text=(
                "✅ <b>To‘lov tasdiqlandi.</b>\n\n"
                "Quyidagi tugma orqali <b>Haydovchilar guruhiga</b> qo‘shiling. "
                "Guruhga qo‘shilgandan so‘ng bu xabar avtomatik o‘chiriladi."
            ),
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        pending_invites[driver_id] = {"msg_id": dm.message_id, "link": invite_link}
        subscriptions[driver_id] = {"active": True}
        trial_members.pop(driver_id, None)
        await message.reply(f"✅ Silka yuborildi: <code>{driver_id}</code>", parse_mode="HTML")
    except Exception:
        await message.reply("❌ Haydovchiga DM yuborib bo‘lmadi (botga /start yozmagan bo‘lishi mumkin).")


@dp.message(Command("test_payments"))
async def test_payments_cmd(message: types.Message) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        await bot.send_message(PAYMENTS_CHAT_ID, "✅ Test: bot cheklar guruhiga xabar yubora oladi.")
        await message.reply("✅ OK: xabar cheklar guruhiga yuborildi.")
    except Exception as exc:
        await message.reply(f"❌ Muvaffaqiyatsiz: {exc}")


@dp.message(Command("test_payments_photo"))
async def test_payments_photo_cmd(message: types.Message) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        url = "https://via.placeholder.com/600x240.png?text=Payments+Photo+Test"
        await bot.send_photo(PAYMENTS_CHAT_ID, url, caption="🧪 Test photo (payments)")
        await message.reply("✅ Rasm cheklar guruhiga yuborildi.")
    except Exception as exc:
        await message.reply(f"❌ Rasm yuborilmadi: {exc}")


@dp.message(Command("users_count"))
async def users_count_cmd(message: types.Message) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return
    total = len(user_profiles or {})
    with_phone = sum(1 for _, profile in (user_profiles or {}).items() if profile.get("phone"))
    await message.reply(
        f"👥 Jami foydalanuvchilar: <b>{total}</b>\n"
        f"📞 Telefon saqlanganlar: <b>{with_phone}</b>",
        parse_mode="HTML",
    )


@dp.message(Command("export_users"))
async def export_users_cmd(message: types.Message) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return

    rows: list[list[str | int]] = []
    for uid, profile in (user_profiles or {}).items():
        rows.append([uid, profile.get("name", ""), profile.get("phone", "")])

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(DATA_DIR, f"users_{timestamp}.csv")

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id", "name", "phone"])
        writer.writerows(rows)

    try:
        await message.answer_document(
            document=FSInputFile(out_path),
            caption=f"👥 Foydalanuvchilar ro‘yxati (CSV) — {len(rows)} ta",
        )
    except Exception as exc:
        await message.reply(f"❌ CSV yuborilmadi: {exc}")


__all__ = []
