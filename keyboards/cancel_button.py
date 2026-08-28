"""
Inline cancel button used by ProgressTracker during active processing.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def cancel_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_processing")]
        ]
    )
