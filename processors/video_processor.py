"""Video processor: YOLO detect once, frame or delogo path, cancel + cleanup."""
from __future__ import annotations
import asyncio
import json
import time
from pathlib import Path
from typing import Optional
from PIL import Image
from config import MAX_LAMA_VIDEO_FRAMES, MAX_OPENCV_VIDEO_FRAMES, VIDEO_REDETECT_INTERVAL
from logger import get_logger
from processors.removal.media_processor import media_processor
from processors.removal.video_frame_pipeline import (
    process_video_frames, should_use_lama_frame_pipeline, should_use_opencv_frame_pipeline,
)
from processors.video_compression import get_video_encoding_args
from services.watermark_service import WatermarkService
from settings_manager import get_orientation, settings
from utilities.progress_tracker import ProgressTracker

logger = get_logger(__name__)

async def _probe(path: Path) -> dict:
    cmd = ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await p.communicate()
    if p.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {err.decode()[:500]}")
    return json.loads(out.decode())

def _extract_duration(info):
    try:
        return float(info["format"]["duration"])
    except Exception:
        for s in info.get("streams", []):
            if s.get("codec_type") == "video" and s.get("duration"):
                return float(s["duration"])
    return 0.0

def _extract_dimensions(info):
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            return int(s["width"]), int(s["height"])
    raise ValueError("No video stream")

def _extract_fps(info):
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            rate = s.get("avg_frame_rate") or s.get("r_frame_rate") or "25/1"
            if "/" in rate:
                n, d = rate.split("/", 1)
                try:
                    df = float(d)
                    return float(n) / df if df else 25.0
                except ValueError:
                    return 25.0
            try:
                return float(rate)
            except ValueError:
                return 25.0
    return 25.0

def _extract_frame_count(info, duration, fps):
    for s in info.get("streams", []):
        if s.get("codec_type") == "video" and s.get("nb_frames"):
            try:
                return int(s["nb_frames"])
            except ValueError:
                pass
    if duration > 0 and fps > 0:
        return int(duration * fps)
    return None

def _has_audio(info):
    return any(s.get("codec_type") == "audio" for s in info.get("streams", []))

async def _grab_first_frame(path):
    def _grab():
        import cv2
        cap = cv2.VideoCapture(str(path))
        frame = None
        ok = False
        for _ in range(6):
            ok, frame = cap.read()
            if ok and frame is not None and frame.size and float(frame.mean()) > 1.0:
                cap.release()
                return frame
        cap.release()
        return frame if ok else None
    return await asyncio.to_thread(_grab)

async def _kill_process(process):
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            pass

async def _wait_with_cancel(process, progress, poll=0.5):
    while process.returncode is None:
        if progress.is_cancelled():
            raise asyncio.CancelledError()
        try:
            await asyncio.wait_for(process.wait(), timeout=poll)
        except asyncio.TimeoutError:
            continue

async def _parse_progress(stdout, duration, progress):
    while True:
        try:
            line = await asyncio.wait_for(stdout.readline(), timeout=5.0)
        except asyncio.TimeoutError:
            continue
        if not line:
            break
        text = line.decode().strip()
        if text.startswith("out_time_ms="):
            try:
                sec = int(text.split("=")[1]) / 1_000_000.0
                await progress.update(min(95, (sec / duration) * 100))
            except Exception:
                pass
        if progress.is_cancelled():
            break

async def _drain_stdout(stdout):
    while True:
        line = await stdout.readline()
        if not line:
            break

async def process_video(input_path, output_path, watermark_service, progress):
    start = time.monotonic()
    await progress.update(5, "Analyzing video...")
    info = await _probe(input_path)
    duration = _extract_duration(info)
    width, height = _extract_dimensions(info)
    fps = _extract_fps(info)
    has_audio = _has_audio(info)
    frame_count = _extract_frame_count(info, duration, fps)
    logger.info("Video %dx%d fps=%.2f dur=%.1fs frames=%s audio=%s", width, height, fps, duration, frame_count, has_audio)
    if progress.is_cancelled():
        raise asyncio.CancelledError()

    orientation = get_orientation(width, height)
    await progress.update(10, "Preparing watermark...")
    wm_path = await watermark_service.prepare_watermark(width, height)
    position = await watermark_service.get_position(orientation)
    has_watermark = wm_path is not None and wm_path.exists()

    removal_enabled = await settings.get_removal_enabled(orientation)
    removal_filter = None
    removal_region = None
    use_frame_pipeline = False
    frame_processor_name = "opencv"

    if removal_enabled:
        await progress.update(12, "Detecting watermark (YOLO)...")
        if progress.is_cancelled():
            raise asyncio.CancelledError()
        rpos = await settings.get_removal_position(orientation)
        rsize = await settings.get_removal_size(orientation)
        frame = await _grab_first_frame(input_path)
        if frame is not None:
            removal_region = await media_processor.detect_video_region(frame, rpos, rsize)
            pname, complexity = await media_processor.select_video_processor(frame, removal_region)
            logger.info("Video region %s complexity=%s selected=%s redetect=%d",
                        removal_region, complexity, pname, VIDEO_REDETECT_INTERVAL)
            if pname == "lama" and should_use_lama_frame_pipeline(frame_count):
                use_frame_pipeline = True
                frame_processor_name = "lama"
            elif should_use_opencv_frame_pipeline(frame_count):
                use_frame_pipeline = True
                frame_processor_name = "opencv"
            else:
                removal_filter = await media_processor.build_video_removal_filter(removal_region)
                logger.info("Long clip: FFmpeg delogo (frames=%s)", frame_count)
        else:
            logger.warning("No first frame; skipping removal")

    if progress.is_cancelled():
        raise asyncio.CancelledError()

    if use_frame_pipeline and removal_region is not None:
        encoding_args = await get_video_encoding_args(orientation)
        try:
            await process_video_frames(
                input_path=input_path, output_path=output_path, region=removal_region,
                fps=fps, has_audio=has_audio, encoding_args=encoding_args,
                processor_name=frame_processor_name,
                watermark_path=wm_path if has_watermark else None,
                watermark_position=position, watermark_service=watermark_service,
                progress=progress,
            )
            await progress.update(100)
            logger.info("Video saved (frames/%s) %.2fs", frame_processor_name, time.monotonic() - start)
        except (asyncio.CancelledError, Exception):
            if Path(output_path).exists():
                try: Path(output_path).unlink()
                except Exception: pass
            raise
        return

    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-progress", "pipe:1", "-nostats"]
    if has_watermark:
        with Image.open(wm_path) as wm_img:
            wm_w, wm_h = wm_img.size
        x, y = watermark_service.calculate_position(position, (wm_w, wm_h), (width, height))
        if removal_filter:
            fc = f"[0:v]{removal_filter}[cleaned];[cleaned][1:v]overlay={x}:{y}:format=auto[v]"
        else:
            fc = f"[0:v][1:v]overlay={x}:{y}:format=auto[v]"
        cmd += ["-i", str(wm_path), "-filter_complex", fc, "-map", "[v]"]
        if has_audio:
            cmd += ["-map", "0:a"]
    elif removal_filter:
        cmd += ["-filter_complex", f"[0:v]{removal_filter}[v]", "-map", "[v]"]
        if has_audio:
            cmd += ["-map", "0:a"]
    else:
        cmd += ["-map", "0:v"]
        if has_audio:
            cmd += ["-map", "0:a"]

    if has_watermark or removal_filter:
        cmd += await get_video_encoding_args(orientation)
    else:
        compression = await settings.get_compression(orientation)
        cmd += ["-c:v", "copy"] if compression == "original" else await get_video_encoding_args(orientation)
    if has_audio:
        cmd += ["-c:a", "copy"]
    cmd += ["-map_metadata", "0", str(output_path)]
    logger.debug("FFmpeg: %s", " ".join(cmd))

    await progress.update(15, "Encoding...")
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stderr_lines = []
    async def _read_err():
        while True:
            line = await process.stderr.readline()
            if not line:
                break
            stderr_lines.append(line.decode(errors="ignore").rstrip())
    err_task = asyncio.create_task(_read_err())
    try:
        if duration > 0:
            prog_task = asyncio.create_task(_parse_progress(process.stdout, duration, progress))
        else:
            prog_task = asyncio.create_task(_drain_stdout(process.stdout))
        await _wait_with_cancel(process, progress)
        prog_task.cancel()
        try:
            await prog_task
        except asyncio.CancelledError:
            pass
        if process.returncode != 0:
            err = "\n".join(stderr_lines[-20:])
            logger.error("FFmpeg failed: %s", err)
            raise RuntimeError(f"FFmpeg failed: {err[:800]}")
        await progress.update(100)
        logger.info("Video saved %s %.2fs", output_path.name, time.monotonic() - start)
    except asyncio.CancelledError:
        logger.info("Video cancelled")
        await _kill_process(process)
        if Path(output_path).exists():
            try: Path(output_path).unlink()
            except Exception: pass
        raise
    except Exception:
        await _kill_process(process)
        if Path(output_path).exists():
            try: Path(output_path).unlink()
            except Exception: pass
        raise
    finally:
        if not err_task.done():
            err_task.cancel()
            try:
                await err_task
            except asyncio.CancelledError:
                pass
