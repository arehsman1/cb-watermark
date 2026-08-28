"""
Bot entry point.

Wires the dispatcher, FSM storage, service middleware, routers,
startup checks, and error handling.
"""

import asyncio
import shutil

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent, Update

from config import BOT_TOKEN
from logger import get_logger
from services.media_service import MediaService
from services.queue_manager import QueueManager
from services.watermark_service import WatermarkService
from utilities.file_manager import FileManager

from handlers import metadata, start, settings, upload_image, upload_video

logger = get_logger("bot")

# Runs for the lifetime of the process (see on_startup/on_shutdown).
# 15 minutes balances catching abandoned files reasonably promptly
# against not burning CPU on a 2 vCPU box for something that's
# already a safety net — per-job cleanup (in each handler's `finally`)
# is what actually keeps disk usage low during normal operation; this
# only catches what that missed (crashes, unexpected exits).
CLEANUP_INTERVAL_SECONDS = 15 * 60
_background_tasks: list[asyncio.Task] = []


# ── Startup ───────────────────────────────────────────────────────────

async def _periodic_cleanup_loop(fm: FileManager) -> None:
    """Sweep temp/uploads/outputs on a fixed interval for the bot's lifetime."""
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            await fm.cleanup_all(max_age_hours=0.5)
            logger.info("Periodic cleanup complete.")
        except asyncio.CancelledError:
            logger.info("Periodic cleanup task stopping.")
            raise
        except Exception as exc:
            # Never let one bad sweep kill the loop — try again next interval.
            logger.error("Periodic cleanup failed (will retry next interval): %s", exc)


async def on_startup(bot: Bot) -> None:
    """Verify FFmpeg, clean stale temp files, and start the periodic cleanup loop."""
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        logger.error("FFmpeg NOT FOUND — video processing will fail!")
    else:
        logger.info("FFmpeg found: %s", ffmpeg_path)

    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        logger.error("FFprobe NOT FOUND — video analysis will fail!")
    else:
        logger.info("FFprobe found: %s", ffprobe_path)

    fm = FileManager()
    await fm.cleanup_all(max_age_hours=0.5)
    logger.info("Startup cleanup complete.")

    task = asyncio.create_task(_periodic_cleanup_loop(fm))
    _background_tasks.append(task)
    logger.info("Periodic cleanup scheduled every %d minutes.", CLEANUP_INTERVAL_SECONDS // 60)


async def on_shutdown(bot: Bot) -> None:
    """Cancel background tasks cleanly on shutdown."""
    for task in _background_tasks:
        task.cancel()
    for task in _background_tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
    _background_tasks.clear()
    logger.info("Background tasks shut down cleanly.")


# ── Error handler ─────────────────────────────────────────────────────

async def error_handler(event: ErrorEvent) -> bool:
    """Catch unhandled exceptions and notify the user safely."""
    logger.error("Unhandled exception: %s", event.exception, exc_info=True)
    try:
        update: Update = event.update
        if update.message:
            await update.message.answer(
                "❌ An unexpected error occurred. Please try again."
            )
        elif update.callback_query:
            await update.callback_query.answer(
                "❌ An error occurred.", show_alert=True
            )
    except Exception:
        pass
    return True


# ── Main ──────────────────────────────────────────────────────────────

def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # ── Services ─────────────────────────────────────────────────────
    fm = FileManager()
    qm = QueueManager()
    ws = WatermarkService()
    ms = MediaService(fm, qm, ws)

    # ── Middleware (function-based, duck-typed) ─────────────────────
    async def services_middleware(handler, event, data):
        data["media_service"] = ms
        data["file_manager"] = fm
        data["queue_manager"] = qm
        data["watermark_service"] = ws
        return await handler(event, data)

    dp.message.middleware(services_middleware)
    dp.callback_query.middleware(services_middleware)

    # ── Routers (most specific first) ────────────────────────────────
    dp.include_router(upload_image.router)
    dp.include_router(upload_video.router)
    dp.include_router(metadata.router)
    dp.include_router(settings.router)
    dp.include_router(start.router)

    # ── Error handler ─────────────────────────────────────────────────
    dp.errors.register(error_handler)

    # ── Startup & polling ───────────────────────────────────────────
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Bot starting...")
    dp.run_polling(bot)


if __name__ == "__main__":
    main()
