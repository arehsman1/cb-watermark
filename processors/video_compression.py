"""
Video encoding parameter generator.

Returns FFmpeg encoding arguments based on the user's compression
setting. Audio is always copied to avoid quality loss.
"""

from logger import get_logger
from settings_manager import Orientation, settings

logger = get_logger(__name__)


async def get_video_encoding_args(orientation: Orientation) -> list[str]:
    """
    Return a list of FFmpeg arguments for video encoding, using the
    compression setting for *orientation* (landscape/portrait).
    Audio is handled separately with -c:a copy.
    """
    compression = await settings.get_compression(orientation)

    # libx264 with yuv420p for maximum compatibility.
    # preset=slow trades CPU for better compression efficiency.
    # CRF values: lower = higher quality / larger file.
    base = ["-c:v", "libx264", "-preset", "slow", "-pix_fmt", "yuv420p"]

    if compression == "original":
        # CRF 18 is considered visually lossless for most content.
        base += ["-crf", "18"]
    elif compression == "high":
        base += ["-crf", "20"]
    elif compression == "medium":
        base += ["-crf", "26"]
    else:
        base += ["-crf", "18"]

    logger.debug("Video compression=%s args=%s", compression, base)
    return base
