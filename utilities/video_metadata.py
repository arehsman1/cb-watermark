"""
Video metadata: read, write, clear.

Reading uses ffprobe exclusively (no re-encoding, just parses the
container). Writing/clearing uses ffmpeg with `-c copy` (stream
copy) so the actual audio/video data is never re-encoded — only the
container-level metadata tags change, which is fast and lossless.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

from logger import get_logger

logger = get_logger(__name__)

# Commonly-present, user-meaningful container tags. Video containers
# don't carry the rich per-shot camera detail JPEGs do (no aperture/
# ISO/GPS-per-frame) — metadata here is file-level: title, author,
# dates, encoder/software, copyright.
EDITABLE_VIDEO_FIELDS = {"title", "artist", "copyright", "comment", "date"}


async def _run_ffprobe(path: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {stderr.decode(errors='ignore')[-500:]}")
    return json.loads(stdout)


def _format_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


async def probe_raw(path: Path) -> dict:
    """Public wrapper around ffprobe's raw JSON output, for callers that need more than read_video_metadata's shaped result (e.g. limit checks)."""
    return await _run_ffprobe(path)


async def read_video_metadata(path: Path) -> dict:
    """
    Read file info + container-level tags from a video.

    Returns a dict with keys: file_info, tags (tags omitted if the
    container has none — callers should not render an empty section).
    """
    info = await _run_ffprobe(path)
    fmt = info.get("format", {})
    video_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)

    file_info = {
        "name": path.name,
        "format": fmt.get("format_long_name", path.suffix.lstrip(".").upper()),
        "size_bytes": path.stat().st_size,
        "duration": _format_duration(float(fmt.get("duration", 0) or 0)),
        "width": video_stream.get("width") if video_stream else None,
        "height": video_stream.get("height") if video_stream else None,
        "codec": video_stream.get("codec_name") if video_stream else None,
    }

    result: dict = {"file_info": file_info}

    raw_tags = {**fmt.get("tags", {}), **(video_stream.get("tags", {}) if video_stream else {})}
    # Normalize keys to lowercase, drop noisy/internal ones nobody wants
    # to see. "language" is dropped only when it's "und" (undefined) —
    # that's MP4/MOV's default track-language marker that FFmpeg writes
    # regardless of -map_metadata, not real user-set metadata; a real
    # language code (e.g. "eng") is still shown.
    tags = {
        k.lower(): v
        for k, v in raw_tags.items()
        if k.lower() not in {"handler_name", "vendor_id", "major_brand", "minor_version", "compatible_brands"}
        and not (k.lower() == "language" and str(v).lower() == "und")
    }
    if tags:
        result["tags"] = tags

    return result


async def clear_video_metadata(input_path: Path, output_path: Path) -> None:
    """Strip all container AND stream-level metadata. Stream copy — no re-encoding."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-map_metadata",
        "-1",
        "-map_metadata:s:v",
        "-1",
        "-map_metadata:s:a",
        "-1",
        "-c",
        "copy",
        str(output_path),
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"Metadata clear failed: {stderr.decode(errors='ignore')[-500:]}")


async def write_video_metadata(input_path: Path, output_path: Path, updates: dict[str, str]) -> None:
    """Apply `updates` (field_name -> value, from EDITABLE_VIDEO_FIELDS) on top of existing tags. Stream copy."""
    cmd = ["ffmpeg", "-y", "-i", str(input_path)]
    for field, value in updates.items():
        if field not in EDITABLE_VIDEO_FIELDS:
            continue
        cmd += ["-metadata", f"{field}={value}"]
    cmd += ["-c", "copy", str(output_path)]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"Metadata write failed: {stderr.decode(errors='ignore')[-500:]}")
