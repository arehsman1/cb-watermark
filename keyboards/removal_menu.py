from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def removal_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🟢 Enable Removal"),
                KeyboardButton(text="🔴 Disable Removal"),
            ],
            [
                KeyboardButton(text="📍 Removal Position"),
                KeyboardButton(text="📏 Search Area Size"),
            ],
            [KeyboardButton(text="⬅️ Back")],
        ],
        resize_keyboard=True,
    )
