from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .bot_instance import bot
from .config import (
    ADMIN_IDS,
    CARD_HOLDER,
    CARD_NUMBER_DISPLAY,
    DRIVERS_CHAT_ID,
    FREE_TRIAL_DAYS,
    SUBSCRIPTION_PRICE,
)
from .state import (
    driver_onboarding,
    pending_invites,
    subscriptions,
    trial_members,
    user_profiles,
)
from .storage import save_users_to_disk

_trial_task: asyncio.Task | None = None


async def _send_trial_invite(uid: int) -> None:
    try:
        granted_at = datetime.now()
        expires_at = granted_at + timedelta(days=FREE_TRIAL_DAYS)
        invite = await bot.create_chat_invite_link(
            chat_id=DRIVERS_CHAT_ID,
            name=f"trial-{uid}",
            member_limit=1,
            expire_date=int(expires_at.timestamp()),
        )
        invite_link = invite.invite_link
    except Exception as exc:
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id, f"❌ Trial silka yaratilmadi (user {uid}): {exc}"
                )
            except Exception:
                pass
        try:
            await bot.send_message(
                uid,
                "❌ Kechirasiz, hozircha trial havola yaratilmayapti. "
                "Iltimos, admin bilan bog‘laning.",
            )
        except Exception:
            pass
        return

    trial_members[uid] = {"expires_at": expires_at}

    profile = user_profiles.setdefault(uid, {})
    profile["trial_granted_at"] = granted_at.isoformat()
    profile["trial_expires_at"] = expires_at.isoformat()
    await save_users_to_disk(user_profiles)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👥 Haydovchilar guruhiga qo‘shilish (30 kun bepul)",
                    url=invite_link,
                )
            ]
        ]
    )
    try:
        dm = await bot.send_message(
            chat_id=uid,
            text=(
                "🎁 <b>30 kunlik bepul sinov</b> faollashtirildi!\n\n"
                f"⏳ Amal qilish muddati: <b>{expires_at.strftime('%Y-%m-%d %H:%M')}</b> gacha.\n"
                "Quyidagi tugma orqali guruhga qo‘shiling. Sinov tugaganda agar obuna "
                "bo‘lmasangiz, guruhdan chiqarib qo‘yiladi."
            ),
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        pending_invites[uid] = {"msg_id": dm.message_id, "link": invite_link}
    except Exception:
        pass


async def trial_watcher() -> None:
    while True:
        try:
            now = datetime.now()
            for uid, info in list(trial_members.items()):
                if subscriptions.get(uid, {}).get("active"):
                    trial_members.pop(uid, None)
                    continue

                expires_at = info.get("expires_at")
                if expires_at and now >= expires_at:
                    try:
                        await bot.ban_chat_member(DRIVERS_CHAT_ID, uid)
                        await bot.unban_chat_member(DRIVERS_CHAT_ID, uid)
                    except Exception:
                        pass

                    price_txt = f"{SUBSCRIPTION_PRICE:,}".replace(",", " ")
                    pay_text = (
                        "⛔️ <b>30 kunlik bepul sinov muddati tugadi.</b>\n\n"
                        f"💳 <b>Obuna to‘lovi:</b> <code>{price_txt} so‘m</code> (1 oy)\n"
                        f"🧾 <b>Karta:</b> <code>{CARD_NUMBER_DISPLAY}</code>\n"
                        f"👤 Karta egasi: <b>{CARD_HOLDER}</b>\n\n"
                        "✅ To‘lovni amalga oshirgach, <b>chek rasm</b>ini yuboring.\n"
                        "Tasdiqlangach, sizga <b>Haydovchilar guruhi</b>ga qayta qo‘shilish havolasini yuboramiz."
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

                    driver_onboarding[uid] = driver_onboarding.get(uid, {})
                    driver_onboarding[uid]["stage"] = "wait_check"

                    try:
                        await bot.send_message(
                            uid,
                            pay_text,
                            parse_mode="HTML",
                            reply_markup=keyboard,
                        )
                    except Exception:
                        pass

                    trial_members.pop(uid, None)
        except Exception:
            pass

        await asyncio.sleep(3600)


def start_trial_watcher() -> asyncio.Task:
    global _trial_task
    if _trial_task is None or _trial_task.done():
        _trial_task = asyncio.create_task(trial_watcher())
    return _trial_task


__all__ = ["_send_trial_invite", "start_trial_watcher", "trial_watcher"]
