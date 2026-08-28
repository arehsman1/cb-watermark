"""
Video upload handler.

Mirrors the image handler flow for video files.
"""

import asyncio
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, KeyboardButton, Message, ReplyKeyboardMarkup

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

@router.message(F.text == "🎥 Upload Video")
async def request_video(message: Message, state: FSMContext, media_service: MediaService) -> None:
    current = await state.get_state()
    if current == BotStates.active_processing.state or await media_service.is_busy():
        await message.answer(
            "⚠️ A file is already being processed.\n\n"
            "Please wait or press ❌ Cancel."
        )
        return

    await state.set_state(BotStates.waiting_video)
    await message.answer(
        "Please send me a video file (MP4, MOV, AVI, MKV).",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="⬅️ Back")]],
            resize_keyboard=True,
        ),
    )


# ── Back navigation ───────────────────────────────────────────────────

@router.message(BotStates.waiting_video, F.text == "⬅️ Back")
async def video_back(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Main menu:", reply_markup=main_menu_kb())


# ── Download handlers ─────────────────────────────────────────────────

@router.message(BotStates.waiting_video, F.video)
async def handle_video(
    message: Message,
    state: FSMContext,
    bot: Bot,
    media_service: MediaService,
    file_manager: FileManager,
) -> None:
    await _process_video(
        message, message.video.file_id, state, bot, media_service, file_manager
    )


@router.message(BotStates.waiting_video, F.document)
async def handle_video_document(
    message: Message,
    state: FSMContext,
    bot: Bot,
    media_service: MediaService,
    file_manager: FileManager,
) -> None:
    await _process_video(
        message, message.document.file_id, state, bot, media_service, file_manager
    )


# ── Core processing flow ──────────────────────────────────────────────

async def _process_video(
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
        await state.set_state(BotStates.active_processing)
        file_info = await bot.get_file(file_id)
        ext = Path(file_info.file_path).suffix or ".mp4"
        input_path = file_manager.generate_unique_path(UPLOADS_DIR, ext)
        await bot.download_file(file_info.file_path, input_path)
    except Exception as exc:
        logger.error("Video download failed: %s", exc)
        await message.answer(
            "❌ Failed to download the video. Please try again.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        if input_path:
            await file_manager.remove(input_path)
        return

    ok, err = await media_service.validate_video(input_path)
    if not ok:
        await file_manager.remove(input_path)
        await message.answer(f"❌ {err}", reply_markup=main_menu_kb())
        await state.clear()
        return

    progress_msg = await message.answer("⏳ Processing...")

    started, job = await media_service.start_processing(
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        message_id=progress_msg.message_id,
        task_type="video",
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
        await media_service.process_video(input_path, job.output_path, progress)
        if progress.is_cancelled():
            raise asyncio.CancelledError()

        await progress.complete()
        await message.answer_document(
            FSInputFile(job.output_path),
            caption="✅ Here is your branded video!",
        )
    except asyncio.CancelledError:
        logger.info("Video processing cancelled for user %d", message.from_user.id)
        await message.answer(
            "❌ Processing cancelled.", reply_markup=main_menu_kb()
        )
    except Exception as exc:
        logger.error("Video processing failed: %s", exc)
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
