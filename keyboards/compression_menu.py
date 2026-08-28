from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def compression_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⭐ Original (No Compression)")],
            [KeyboardButton(text="⭐⭐ High Quality")],
            [KeyboardButton(text="⭐⭐⭐ Medium Quality")],
            [KeyboardButton(text="⬅️ Back")],
        ],
        resize_keyboard=True,
    )
