from __future__ import annotations

from datetime import datetime, time as dtime


def is_hhmm(value: str) -> bool:
    try:
        datetime.strptime(value, "%H:%M")
        return True
    except Exception:
        return False


def normalize_hhmm(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%H:%M").time()
        return parsed.strftime("%H:%M")
    except Exception:
        return value


def phone_display(phone: str | None) -> str:
    if not phone:
        return "—"
    phone = str(phone)
    return phone if phone.startswith("+") else f"+{phone}"


def human_dt(dt_str: str | None) -> str:
    if not dt_str:
        return "—"
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return dt_str


def event_dt_today_or_now(hhmm: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    try:
        hours, minutes = map(int, hhmm.split(":"))
        target = datetime.combine(now.date(), dtime(hour=hours, minute=minutes))
    except Exception:
        return now
    return target if target > now else now


__all__ = [
    "event_dt_today_or_now",
    "human_dt",
    "is_hhmm",
    "normalize_hhmm",
    "phone_display",
]
