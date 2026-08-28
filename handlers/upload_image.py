"""
Image upload handler.

Handles main-menu button, back navigation, photo/document downloads,
validation, queueing, processing, cancellation, and cleanup.
"""

import asyncio
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, KeyboardButton, Message, ReplyKeyboardMarkup

from config import UPLOADS_DIR
from keyboards.main_menu import main_menu_kb
from logger import get_logger
from services.media_service import MediaService
from states import BotStates
from utilities.file_manager import FileManager
from utilities.progress_tracker import ProgressTracker

logger = get_logger(__name__)
router = Router()


# ── Entry point ───────────────────────────────────────────────────────

@router.message(F.text == "📷 Upload Image")
async def request_image(message: Message, state: FSMContext, media_service: MediaService) -> None:
    current = await state.get_state()
    if current == BotStates.active_processing.state or await media_service.is_busy():
        await message.answer(
            "⚠️ A file is already being processed.\n\n"
            "Please wait or press ❌ Cancel."
        )
        return

    await state.set_state(BotStates.waiting_image)
    await message.answer(
        "Please send me an image file (JPG, JPEG, PNG, WEBP).",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="⬅️ Back")]],
            resize_keyboard=True,
        ),
    )


# ── Back navigation ───────────────────────────────────────────────────

@router.message(BotStates.waiting_image, F.text == "⬅️ Back")
async def image_back(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Main menu:", reply_markup=main_menu_kb())


# ── Download handlers ─────────────────────────────────────────────────

@router.message(BotStates.waiting_image, F.photo)
async def handle_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
    media_service: MediaService,
    file_manager: FileManager,
) -> None:
    photo = message.photo[-1]
    await _process_image(message, photo.file_id, state, bot, media_service, file_manager)


@router.message(BotStates.waiting_image, F.document)
async def handle_image_document(
    message: Message,
    state: FSMContext,
    bot: Bot,
    media_service: MediaService,
    file_manager: FileManager,
) -> None:
    await _process_image(
        message, message.document.file_id, state, bot, media_service, file_manager
    )


# ── Core processing flow ──────────────────────────────────────────────

async def _process_image(
    message: Message,
    file_id: str,
    state: FSMContext,
    bot: Bot,
    media_service: MediaService,
    file_manager: FileManager,
) -> None:
    if await media_service.is_busy():
        await message.answer(
            "⚠️ A file is already being processed.\n\n"
            "Please wait or press ❌ Cancel."
        )
        return

    input_path: Path | None = None
    job = None

    try:
        # Download
        await state.set_state(BotStates.active_processing)
        file_info = await bot.get_file(file_id)
        ext = Path(file_info.file_path).suffix or ".jpg"
        input_path = file_manager.generate_unique_path(UPLOADS_DIR, ext)
        await bot.download_file(file_info.file_path, input_path)
    except Exception as exc:
        logger.error("Image download failed: %s", exc)
        await message.answer(
            "❌ Failed to download the image. Please try again.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        if input_path:
            await file_manager.remove(input_path)
        return

    # Validate
    ok, err = await media_service.validate_image(input_path)
    if not ok:
        await file_manager.remove(input_path)
        await message.answer(f"❌ {err}", reply_markup=main_menu_kb())
        await state.clear()
        return

    # Queue and process
    progress_msg = await message.answer("⏳ Processing...")

    started, job = await media_service.start_processing(
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        message_id=progress_msg.message_id,
        task_type="image",
        input_path=input_path,
    )

    if not started or job is None:
        await file_manager.remove(input_path)
        try:
            await progress_msg.edit_text(
                "⚠️ A file is already being processed.\n\n"
                "Please wait or press ❌ Cancel."
            )
        except Exception:
            pass
        await state.clear()
        return

    progress = ProgressTracker(
        bot, message.chat.id, progress_msg.message_id, job.cancel_event
    )

    try:
        await media_service.process_image(input_path, job.output_path, progress)
        if progress.is_cancelled():
            raise asyncio.CancelledError()

        await progress.complete()
        await message.answer_document(
            FSInputFile(job.output_path),
            caption="✅ Here is your branded image!",
        )
    except asyncio.CancelledError:
        logger.info("Image processing cancelled for user %d", message.from_user.id)
        await message.answer(
            "❌ Processing cancelled.", reply_markup=main_menu_kb()
        )
    except Exception as exc:
        logger.error("Image processing failed: %s", exc)
        await progress.fail("Processing error")
        await message.answer(
            "❌ Processing failed. Please try again.", reply_markup=main_menu_kb()
        )
    finally:
        try:
            await media_service.finish_processing(message.from_user.id)
        except Exception as exc:
            logger.error("Failed to finish processing: %s", exc)
        try:
            if input_path:
                await file_manager.remove(input_path)
        except Exception:
            pass
        try:
            if job and job.output_path.exists():
                await file_manager.remove(job.output_path)
        except Exception:
            pass
        try:
            await state.clear()
        except Exception:
            pass


# ── Cancel callback (shared with video) ─────────────────────────────────

@router.callback_query(F.data == "cancel_processing")
async def cancel_processing(callback: CallbackQuery, media_service: MediaService) -> None:
    cancelled = await media_service.cancel_processing(callback.from_user.id)
    if cancelled:
        await callback.answer("Cancellation requested...", show_alert=False)
    else:
        await callback.answer("No active processing to cancel.", show_alert=True)
