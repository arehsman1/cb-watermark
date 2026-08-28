from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def position_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="↖️ Top Left"),
                KeyboardButton(text="↗️ Top Right"),
            ],
            [
                KeyboardButton(text="↙️ Bottom Left"),
                KeyboardButton(text="↘️ Bottom Right"),
            ],
            [KeyboardButton(text="🎯 Center")],
            [KeyboardButton(text="⬅️ Back")],
        ],
        resize_keyboard=True,
    )
