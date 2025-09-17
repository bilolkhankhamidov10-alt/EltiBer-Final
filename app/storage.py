from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from .config import DATA_DIR

USERS_JSON = os.path.join(DATA_DIR, "users.json")
STORE_LOCK = asyncio.Lock()


def _ensure_data_dir() -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception:
        pass


def _load_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


async def _save_json(path: str, data: Any) -> None:
    _ensure_data_dir()
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


def load_users_from_disk() -> dict:
    raw = _load_json(USERS_JSON, {})
    fixed: dict = {}
    for k, v in (raw or {}).items():
        try:
            ik = int(k)
        except (ValueError, TypeError):
            ik = k
        fixed[ik] = v
    return fixed


async def save_users_to_disk(users: dict) -> None:
    async with STORE_LOCK:
        await _save_json(USERS_JSON, {str(k): v for k, v in (users or {}).items()})


__all__ = [
    "USERS_JSON",
    "STORE_LOCK",
    "load_users_from_disk",
    "save_users_to_disk",
]
