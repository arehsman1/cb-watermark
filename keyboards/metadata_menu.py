from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def metadata_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👁️ View Metadata")],
            [KeyboardButton(text="✏️ Edit Metadata")],
            [KeyboardButton(text="🗑️ Clear Metadata")],
            [KeyboardButton(text="⬅️ Back")],
        ],
        resize_keyboard=True,
    )
