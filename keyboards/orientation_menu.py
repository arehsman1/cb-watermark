from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def orientation_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📍 Watermark Position"),
                KeyboardButton(text="🌫️ Watermark Opacity"),
            ],
            [KeyboardButton(text="🗜️ Compression Quality")],
            [KeyboardButton(text="🧹 Old Watermark Removal")],
            [KeyboardButton(text="⬅️ Back")],
        ],
        resize_keyboard=True,
    )
