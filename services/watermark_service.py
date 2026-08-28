"""
Watermark preparation.

Generates a scaled, opacity-adjusted PNG ready for compositing onto
images (via Pillow) or videos (via FFmpeg overlay).
"""

import asyncio
import uuid
from pathlib import Path
from typing import Optional

from PIL import Image

from config import TEMP_DIR
from logger import get_logger
from settings_manager import Orientation, SettingsManager, get_orientation, settings

logger = get_logger(__name__)


class WatermarkService:
    """
    Async service that reads the user's PNG watermark, scales it to
    ~15 % of the target media width (never upscaling), applies the
    configured opacity for the media's orientation, and writes a
    temporary PNG for processors.
    """

    def __init__(self, settings_manager: SettingsManager = settings) -> None:
        self._settings = settings_manager

    async def prepare_watermark(
        self,
        media_width: int,
        media_height: int,
        temp_dir: Path = TEMP_DIR,
    ) -> Optional[Path]:
        """
        Create a processed watermark image.

        Returns the path to the temp watermark, or None if no watermark
        has been uploaded yet.
        """
        wm_path = await self._settings.get_watermark_path()
        if not wm_path.exists():
            logger.warning("No watermark found at %s", wm_path)
            return None

        orientation = get_orientation(media_width, media_height)
        opacity = await self._settings.get_opacity(orientation)

        def _process() -> Path:
            with Image.open(wm_path) as img:
                # Ensure RGBA so alpha compositing works correctly
                if img.mode != "RGBA":
                    img = img.convert("RGBA")

                # Scale to ~15 % of media width, never upscale beyond original
                target_width = int(media_width * 0.15)
                if target_width > img.width:
                    target_width = img.width

                aspect = img.height / img.width
                target_height = int(target_width * aspect)

                # High-quality Lanczos resampling
                img = img.resize((target_width, target_height), Image.LANCZOS)

                # Apply opacity by mutating the alpha channel
                if opacity < 1.0:
                    alpha = img.getchannel("A")
                    alpha = alpha.point(lambda p: int(p * opacity))
                    img.putalpha(alpha)

                out_name = f"wm_{media_width}_{uuid.uuid4().hex}.png"
                out_path = temp_dir / out_name
                img.save(out_path, "PNG")
                return out_path

        try:
            result = await asyncio.to_thread(_process)
            logger.info("Prepared watermark: %s (%d px wide)", result.name, media_width)
            return result
        except Exception as exc:
            logger.error("Failed to prepare watermark: %s", exc)
            return None

    async def get_position(self, orientation: Orientation) -> str:
        return await self._settings.get_position(orientation)

    def calculate_position(
        self,
        position_str: str,
        wm_size: tuple[int, int],
        media_size: tuple[int, int],
    ) -> tuple[int, int]:
        """
        Return (x, y) top-left coordinates for the watermark.
        """
        w, h = wm_size
        mw, mh = media_size
        margin = max(int(mw * 0.02), 10)

        positions: dict[str, tuple[int, int]] = {
            "top-left": (margin, margin),
            "top-right": (mw - w - margin, margin),
            "bottom-left": (margin, mh - h - margin),
            "bottom-right": (mw - w - margin, mh - h - margin),
            "center": ((mw - w) // 2, (mh - h) // 2),
        }
        return positions.get(position_str, positions["bottom-right"])
