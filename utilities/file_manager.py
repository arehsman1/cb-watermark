"""
File management utilities.

Handles unique path generation, MIME/extension validation, disk-space
checks, and aggressive cleanup to protect Render's limited free disk.
"""

import asyncio
import shutil
import time
import uuid
from pathlib import Path

from config import MAX_IMAGE_PIXELS, MAX_INPUT_SIZE, OUTPUTS_DIR, TEMP_DIR, UPLOADS_DIR
from logger import get_logger

logger = get_logger(__name__)


class FileManager:
    """
    Centralized file operations.

    All path generation goes through here so temp/output files are
    consistently named, tracked, and removed.
    """

    def __init__(
        self,
        uploads: Path = UPLOADS_DIR,
        outputs: Path = OUTPUTS_DIR,
        temp: Path = TEMP_DIR,
    ) -> None:
        self.uploads = uploads
        self.outputs = outputs
        self.temp = temp

    # ── Path generation ───────────────────────────────────────────────

    def generate_unique_path(self, directory: Path, suffix: str) -> Path:
        """Return a randomly-named path inside *directory*."""
        return directory / f"{uuid.uuid4().hex}{suffix}"

    # ── Validation ────────────────────────────────────────────────────

    def get_size(self, path: Path) -> int:
        """Return file size in bytes, or 0 if missing."""
        return path.stat().st_size if path.exists() else 0

    def check_disk_space(self, required_mb: int = 200) -> bool:
        """Return True if at least *required_mb* are free on the temp disk."""
        try:
            check_path = self.temp if self.temp.exists() else Path(".")
            usage = shutil.disk_usage(check_path)
            available_mb = usage.free // (1024 * 1024)
            return available_mb >= required_mb
        except Exception as exc:
            logger.warning("Disk-space check failed: %s", exc)
            return True  # permissive if we cannot check

    async def validate_upload(
        self,
        path: Path,
        allowed_extensions: set[str],
        max_size: int = MAX_INPUT_SIZE,
    ) -> tuple[bool, str]:
        """
        Validate a downloaded file.

        Returns (ok, error_message).
        """
        if not path.exists():
            return False, "File not found after download."

        size = self.get_size(path)
        if size == 0:
            return False, "Downloaded file is empty."

        if size > max_size:
            return (
                False,
                f"File too large ({size / 1024 / 1024:.1f} MB). "
                f"Max allowed: {max_size / 1024 / 1024:.1f} MB.",
            )

        if path.suffix.lower() not in allowed_extensions:
            ext_list = ", ".join(sorted(allowed_extensions))
            return False, f"Unsupported extension '{path.suffix}'. Supported: {ext_list}"

        # Require 3× input size free (input + temp + output)
        needed_mb = max(200, (size * 3) // (1024 * 1024))
        if not self.check_disk_space(required_mb=needed_mb):
            return False, "Insufficient disk space to process this file safely."

        return True, ""

    def check_image_pixel_limit(
        self, path: Path, max_pixels: int = MAX_IMAGE_PIXELS
    ) -> tuple[bool, str]:
        """
        Guard against decompression-bomb-style images: a small file
        on disk (e.g. a solid-color PNG) can still decode to an
        enormous in-memory pixel buffer. Image.open() is lazy — it
        only reads the header until pixel data is actually accessed
        — so this check is cheap even for the images it's protecting
        against; it never decodes the full bitmap just to check size.
        """
        try:
            from PIL import Image

            with Image.open(path) as img:
                width, height = img.size
        except Exception as exc:
            return False, f"Could not read image dimensions: {exc}"

        pixels = width * height
        if pixels > max_pixels:
            return False, (
                f"Image dimensions too large ({width}x{height} = "
                f"{pixels / 1_000_000:.0f}MP). Max: {max_pixels / 1_000_000:.0f}MP."
            )
        return True, ""

    # ── Cleanup ───────────────────────────────────────────────────────

    async def remove(self, path: Path) -> None:
        """Idempotent async file removal."""
        if not path.exists():
            return
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, path.unlink)
            logger.debug("Removed file: %s", path)
        except Exception as exc:
            logger.warning("Failed to remove %s: %s", path, exc)

    async def remove_dir(self, path: Path) -> None:
        """
        Idempotent async recursive directory removal. Used for
        per-job temp folders (e.g. extracted video frames) that
        `remove()` can't handle since it only unlinks single files.
        """
        if not path.exists():
            return
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: shutil.rmtree(path, ignore_errors=True))
            logger.debug("Removed directory: %s", path)
        except Exception as exc:
            logger.warning("Failed to remove directory %s: %s", path, exc)

    async def cleanup_directory(self, directory: Path, max_age_hours: float = 0.5) -> None:
        """Remove files AND abandoned subdirectories older than *max_age_hours* from *directory*."""
        if not directory.exists():
            return

        now = time.time()
        cutoff = now - (max_age_hours * 3600)

        for f in directory.iterdir():
            try:
                if f.stat().st_mtime >= cutoff:
                    continue
                if f.is_dir():
                    await self.remove_dir(f)
                    logger.info("Cleaned up abandoned directory: %s", f)
                else:
                    await self.remove(f)
                    logger.info("Cleaned up abandoned file: %s", f)
            except Exception as exc:
                logger.warning("Failed to stat/remove %s: %s", f, exc)

    async def cleanup_all(self, max_age_hours: float = 0.5) -> None:
        """Clean temp, uploads, and outputs directories."""
        for directory in (self.temp, self.uploads, self.outputs):
            await self.cleanup_directory(directory, max_age_hours)


# Singleton instance for modules that don't receive one via DI
# (e.g. the video frame pipeline, which isn't a Telegram handler).
file_manager = FileManager()
