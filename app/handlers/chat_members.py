from __future__ import annotations

from datetime import datetime

from aiogram import types

from ..bot_instance import bot, dp
from ..config import DRIVERS_CHAT_ID
from ..state import pending_invites, user_profiles
from ..storage import save_users_to_disk


@dp.chat_member()
async def on_chat_member(update: types.ChatMemberUpdated) -> None:
    try:
        if update.chat.id != DRIVERS_CHAT_ID:
            return
        old_status = update.old_chat_member.status
        new_status = update.new_chat_member.status
        user = update.new_chat_member.user
        if new_status in ("member", "administrator") and old_status in ("left", "kicked"):
            pending = pending_invites.pop(user.id, None)
            if pending:
                try:
                    await bot.delete_message(chat_id=user.id, message_id=pending["msg_id"])
                except Exception:
                    pass
                try:
                    await bot.send_message(user.id, "🎉 Guruhga muvaffaqiyatli qo‘shildingiz! Ishingizga omad.")
                except Exception:
                    pass
            profile = user_profiles.setdefault(user.id, {})
            if profile.get("trial_granted_at") and not profile.get("trial_joined_at"):
                profile["trial_joined_at"] = datetime.now().isoformat()
                await save_users_to_disk(user_profiles)
    except Exception:
        pass
