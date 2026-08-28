from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def opacity_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="100%"),
                KeyboardButton(text="80%"),
                KeyboardButton(text="60%"),
            ],
            [
                KeyboardButton(text="40%"),
                KeyboardButton(text="20%"),
            ],
            [KeyboardButton(text="⬅️ Back")],
        ],
        resize_keyboard=True,
    )
