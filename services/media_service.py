"""
Media orchestration layer.

Validates uploads, manages queue state, and delegates to image/video
processors.  Processor imports are deferred (inside methods) to avoid
circular import issues while the project is being built step-by-step.
"""

from pathlib import Path
from typing import Optional

from config import IMAGE_EXTENSIONS, MAX_INPUT_SIZE, OUTPUTS_DIR, VIDEO_EXTENSIONS
from logger import get_logger
from services.queue_manager import Job, QueueManager
from services.watermark_service import WatermarkService
from utilities.file_manager import FileManager
from utilities.progress_tracker import ProgressTracker

logger = get_logger(__name__)


class MediaService:
    """
    High-level service used by Telegram handlers.

    Flow:
        1. validate_*()
        2. start_processing()  (queues the job)
        3. process_*()           (calls processor, wrapped in try/finally)
        4. finish_processing()   (releases queue)
    """

    def __init__(
        self,
        file_manager: FileManager,
        queue_manager: QueueManager,
        watermark_service: WatermarkService,
    ) -> None:
        self._file_manager = file_manager
        self._queue = queue_manager
        self._watermark = watermark_service

    # ── Validation ──────────────────────────────────────────────────────

    async def validate_image(self, path: Path) -> tuple[bool, str]:
        ok, err = await self._file_manager.validate_upload(
            path=path,
            allowed_extensions=IMAGE_EXTENSIONS,
            max_size=MAX_INPUT_SIZE,
        )
        if not ok:
            return ok, err
        return self._file_manager.check_image_pixel_limit(path)

    async def validate_video(self, path: Path) -> tuple[bool, str]:
        return await self._file_manager.validate_upload(
            path=path,
            allowed_extensions=VIDEO_EXTENSIONS,
            max_size=MAX_INPUT_SIZE,
        )

    # ── Queue management ──────────────────────────────────────────────

    async def is_busy(self) -> bool:
        """Return True if the processing queue is currently occupied."""
        return await self._queue.is_busy()

    async def start_processing(
        self,
        user_id: int,
        chat_id: int,
        message_id: int,
        task_type: str,
        input_path: Path,
    ) -> tuple[bool, Optional[Job]]:
        """
        Reserve a queue slot.

        Returns (success, job_or_none).
        """
        # Preserve original file extension so FFmpeg / Pillow emit the right format
        output_path = self._file_manager.generate_unique_path(
            OUTPUTS_DIR, input_path.suffix
        )

        job = Job(
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            task_type=task_type,
            input_path=input_path,
            output_path=output_path,
        )

        if not await self._queue.start_job(job):
            return False, None

        return True, job

    async def finish_processing(self, user_id: int) -> None:
        """Release the queue slot."""
        await self._queue.finish_job(user_id)

    async def cancel_processing(self, user_id: int) -> bool:
        """Signal cancellation for the active job."""
        return await self._queue.cancel_job(user_id)

    # ── Processing delegation ───────────────────────────────────────────

    async def process_image(
        self,
        input_path: Path,
        output_path: Path,
        progress: ProgressTracker,
    ) -> None:
        """
        Apply watermark and compression to an image.

        Import is deferred so this module loads before processors exist.
        """
        from processors.image_processor import process_image

        await process_image(
            input_path=input_path,
            output_path=output_path,
            watermark_service=self._watermark,
            progress=progress,
        )

    async def process_video(
        self,
        input_path: Path,
        output_path: Path,
        progress: ProgressTracker,
    ) -> None:
        """
        Apply watermark and compression to a video.

        Import is deferred so this module loads before processors exist.
        """
        from processors.video_processor import process_video

        await process_video(
            input_path=input_path,
            output_path=output_path,
            watermark_service=self._watermark,
            progress=progress,
        )

    # ── Cleanup ─────────────────────────────────────────────────────────

    async def cleanup(self, *paths: Path) -> None:
        """Remove one or more files safely."""
        for p in paths:
            await self._file_manager.remove(p)
