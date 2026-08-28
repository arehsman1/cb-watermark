"""
Image compression parameter generator.

Returns Pillow save kwargs based on the user's compression setting.
PNG is treated as lossless; we only toggle optimize.
"""

from typing import Any

from logger import get_logger
from settings_manager import Orientation, settings

logger = get_logger(__name__)


async def get_save_kwargs(image_format: str, orientation: Orientation) -> dict[str, Any]:
    """
    Return Pillow save kwargs for the given format and the current
    compression setting for *orientation* (landscape/portrait).
    """
    compression = await settings.get_compression(orientation)
    kwargs: dict[str, Any] = {}

    fmt = image_format.upper()

    if fmt == "JPEG":
        # JPEG has no lossless mode in Pillow — quality=95 is the
        # accepted "visually lossless" ceiling for this format.
        if compression == "original":
            kwargs["quality"] = 95
            kwargs["optimize"] = True
        elif compression == "high":
            kwargs["quality"] = 90
            kwargs["optimize"] = True
        elif compression == "medium":
            kwargs["quality"] = 80
            kwargs["optimize"] = True
        else:
            kwargs["quality"] = 95
            kwargs["optimize"] = True

    elif fmt == "WEBP":
        if compression == "original":
            # True lossless — quality=95 is still LOSSY and was
            # silently degrading detailed images despite the
            # "no compression" label (verified: up to 118/255 pixel
            # deviation on noisy content). lossless=True guarantees
            # zero deviation from the source pixels.
            kwargs["lossless"] = True
        elif compression == "high":
            kwargs["quality"] = 90
            kwargs["optimize"] = True
        elif compression == "medium":
            kwargs["quality"] = 80
            kwargs["optimize"] = True
        else:
            kwargs["lossless"] = True

    elif fmt == "PNG":
        # PNG is lossless; avoid lossy re-compression.
        # optimize=True is harmless and saves a few bytes.
        kwargs["optimize"] = True
        if compression != "original":
            logger.info("PNG compression requested but skipped (lossless format)")

    else:
        # Fallback for unknown formats
        kwargs["quality"] = 95

    logger.debug("Compression=%s format=%s kwargs=%s", compression, fmt, kwargs)
    return kwargs
