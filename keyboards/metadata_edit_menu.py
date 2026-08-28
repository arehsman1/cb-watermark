from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

IMAGE_EDIT_FIELD_LABELS = {
    "Artist": "artist",
    "Copyright": "copyright",
    "Software": "software",
    "Date Modified": "date_modified",
}

VIDEO_EDIT_FIELD_LABELS = {
    "Title": "title",
    "Artist": "artist",
    "Copyright": "copyright",
    "Comment": "comment",
}


def image_edit_field_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label)] for label in IMAGE_EDIT_FIELD_LABELS]
        + [[KeyboardButton(text="⬅️ Back")]],
        resize_keyboard=True,
    )


def video_edit_field_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label)] for label in VIDEO_EDIT_FIELD_LABELS]
        + [[KeyboardButton(text="⬅️ Back")]],
        resize_keyboard=True,
    )
