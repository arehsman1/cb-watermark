from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def removal_size_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔹 Small (~20%)")],
            [KeyboardButton(text="🔸 Medium (~30%)")],
            [KeyboardButton(text="🔶 Large (~40%)")],
            [KeyboardButton(text="⬅️ Back")],
        ],
        resize_keyboard=True,
    )
