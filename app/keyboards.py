from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from .config import (
    BACK,
    BOSHQA,
    CANCEL,
    CONTACT_BTN,
    DRIVER_BTN,
    HOZIR,
)


def rows_from_list(items: list[str], per_row: int = 3) -> list[list[KeyboardButton]]:
    return [
        [KeyboardButton(text=text) for text in items[i : i + per_row]]
        for i in range(0, len(items), per_row)
    ]


def keyboard_with_back_cancel(
    options: list[str],
    per_row: int = 3,
    show_back: bool = True,
) -> ReplyKeyboardMarkup:
    rows = rows_from_list(options or [], per_row=per_row)
    tail: list[KeyboardButton] = []
    if show_back:
        tail.append(KeyboardButton(text=BACK))
    tail.append(KeyboardButton(text=CANCEL))
    rows.append(tail)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def vehicle_keyboard() -> ReplyKeyboardMarkup:
    vehicles = ["🛻 Labo", "🚚 Labodan Kattaroq"]
    return keyboard_with_back_cancel(vehicles, per_row=1, show_back=False)


def contact_keyboard(text: str = "📲 Telefon raqamni yuborish") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text, request_contact=True)]],
        resize_keyboard=True,
    )


def share_phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📲 Telefon raqamini ulashish", request_contact=True)],
            [KeyboardButton(text=BACK), KeyboardButton(text=CANCEL)],
        ],
        resize_keyboard=True,
    )


def pickup_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True)],
            [KeyboardButton(text=BACK), KeyboardButton(text=CANCEL)],
        ],
        resize_keyboard=True,
    )


def order_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚖 Buyurtma berish")],
            [KeyboardButton(text=DRIVER_BTN)],
            [KeyboardButton(text=CONTACT_BTN)],
        ],
        resize_keyboard=True,
    )


def when_keyboard() -> ReplyKeyboardMarkup:
    return keyboard_with_back_cancel([HOZIR, BOSHQA], per_row=2, show_back=True)


__all__ = [
    "contact_keyboard",
    "keyboard_with_back_cancel",
    "order_keyboard",
    "pickup_keyboard",
    "rows_from_list",
    "share_phone_keyboard",
    "vehicle_keyboard",
    "when_keyboard",
]
