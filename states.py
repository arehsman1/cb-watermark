"""
aiogram 3 FSM states.

The active_processing state is set while a user's job is running so
the UI can reject additional uploads from the same user.
"""

from aiogram.fsm.state import State, StatesGroup


class BotStates(StatesGroup):
    waiting_image = State()
    waiting_video = State()
    waiting_watermark = State()
    settings = State()
    orientation_settings = State()
    position = State()
    opacity = State()
    compression = State()
    removal = State()
    removal_position = State()
    removal_size = State()
    active_processing = State()
    waiting_metadata_file = State()
    metadata_menu = State()
    metadata_edit_field = State()
    metadata_edit_value = State()
