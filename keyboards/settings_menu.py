from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def settings_menu_kb() -> ReplyKeyboardMarkup:
    """Top-level settings menu: shared watermark image + orientation picker."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🖼️ Set Watermark")],
            [
                KeyboardButton(text="📐 Landscape Settings"),
                KeyboardButton(text="📱 Portrait Settings"),
            ],
            [KeyboardButton(text="⬅️ Back")],
        ],
        resize_keyboard=True,
    )
