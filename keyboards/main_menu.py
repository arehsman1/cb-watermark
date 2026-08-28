from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📷 Upload Image"),
                KeyboardButton(text="🎥 Upload Video"),
            ],
            [KeyboardButton(text="📋 Metadata Tools")],
            [KeyboardButton(text="⚙️ Settings")],
        ],
        resize_keyboard=True,
    )
