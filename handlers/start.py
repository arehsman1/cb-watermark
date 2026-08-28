"""
/start handler and main menu entry point.
"""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from keyboards.main_menu import main_menu_kb
from states import BotStates

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Clear any stale state and show the main menu."""
    await state.clear()
    await message.answer(
        "Welcome to Branding Bot! 🎨\n\n"
        "Apply your custom watermark to images and videos.\n\n"
        "Choose an option below:",
        reply_markup=main_menu_kb(),
    )
