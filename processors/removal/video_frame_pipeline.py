"""Frame-by-frame video watermark removal (OpenCV or LaMa)."""
from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image
from config import MAX_LAMA_VIDEO_FRAMES, MAX_OPENCV_VIDEO_FRAMES, TEMP_DIR
from logger import get_logger
from processors.removal.lama_processor import LamaProcessor
from processors.removal.opencv_processor import OpenCVProcessor
from services.watermark_service import WatermarkService
from utilities.file_manager import FileManager, file_manager as default_file_manager
from utilities.progress_tracker import ProgressTracker

logger = get_logger(__name__)
Region = Tuple[int, int, int, int]

def should_use_lama_frame_pipeline(frame_count: Optional[int]) -> bool:
    return frame_count is not None and frame_count <= MAX_LAMA_VIDEO_FRAMES

def should_use_opencv_frame_pipeline(frame_count: Optional[int]) -> bool:
    return frame_count is not None and frame_count <= MAX_OPENCV_VIDEO_FRAMES

def should_use_frame_pipeline(frame_count: Optional[int]) -> bool:
    return should_use_lama_frame_pipeline(frame_count)

async def _extract_frames(input_path: Path, frames_dir: Path) -> list[Path]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-vsync", "0", str(frames_dir / "frame_%06d.png")]
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"Frame extraction failed: {stderr.decode(errors='ignore')[-500:]}")
    return sorted(frames_dir.glob("frame_*.png"))

async def _rebuild_video(frames_dir, output_path, fps, input_path, has_audio, encoding_args):
    fps_str = f"{fps:.6f}".rstrip("0").rstrip(".")
    cmd = [
        "ffmpeg", "-y", "-framerate", fps_str,
        "-i", str(frames_dir / "frame_%06d.png"), "-i", str(input_path),
        *encoding_args, "-map", "0:v:0",
    ]
    if has_audio:
        cmd += ["-map", "1:a:0?", "-c:a", "copy"]
    cmd += ["-shortest", "-map_metadata", "1", str(output_path)]
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await process.communicate()
    if process.returncode != 0 and has_audio:
        logger.warning("Audio copy failed; retrying with AAC")
        cmd2 = [
            "ffmpeg", "-y", "-framerate", fps_str,
            "-i", str(frames_dir / "frame_%06d.png"), "-i", str(input_path),
            *encoding_args, "-map", "0:v:0", "-map", "1:a:0?",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-map_metadata", "1",
            str(output_path),
        ]
        p2 = await asyncio.create_subprocess_exec(
            *cmd2, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
        )
        _, e2 = await p2.communicate()
        if p2.returncode != 0:
            raise RuntimeError(f"Rebuild failed: {e2.decode(errors='ignore')[-800:]}")
    elif process.returncode != 0:
        raise RuntimeError(f"Rebuild failed: {stderr.decode(errors='ignore')[-800:]}")

async def process_video_frames(
    input_path, output_path, region, fps, has_audio, encoding_args,
    processor_name, watermark_path, watermark_position, watermark_service,
    progress, manager: FileManager = default_file_manager,
):
    use_lama = processor_name == "lama"
    job_dir = manager.generate_unique_path(TEMP_DIR, "_vframes")
    opencv = OpenCVProcessor()
    lama = LamaProcessor() if use_lama else None
    try:
        if progress.is_cancelled():
            raise asyncio.CancelledError()
        await progress.update(15, "Extracting frames...")
        frame_paths = await _extract_frames(input_path, job_dir)
        total = len(frame_paths)
        if total == 0:
            raise RuntimeError("No frames extracted.")
        logger.info("Frame pipeline processor=%s frames=%d region=%s", processor_name, total, region)
        wm_overlay = None
        if watermark_path and Path(watermark_path).exists():
            with Image.open(watermark_path) as wm:
                wm_overlay = wm.convert("RGBA").copy()

        async def _one(fp: Path):
            with Image.open(fp) as frame_img:
                base = frame_img.convert("RGB")
                cleaned = await (lama.remove(base, region) if use_lama and lama else opencv.remove(base, region))
                if wm_overlay is not None:
                    x, y = watermark_service.calculate_position(watermark_position, wm_overlay.size, cleaned.size)
                    cleaned = cleaned.convert("RGBA")
                    cleaned.alpha_composite(wm_overlay, (x, y))
                    cleaned = cleaned.convert("RGB")
                cleaned.save(fp, format="PNG")

        if use_lama and lama is not None:
            async with lama.loaded_session():
                for i, fp in enumerate(frame_paths):
                    if progress.is_cancelled():
                        raise asyncio.CancelledError()
                    await _one(fp)
                    if i % 5 == 0 or i == total - 1:
                        await progress.update(15 + int(60 * (i + 1) / total), f"Removing watermark (frame {i+1}/{total})...")
        else:
            for i, fp in enumerate(frame_paths):
                if progress.is_cancelled():
                    raise asyncio.CancelledError()
                await _one(fp)
                if i % 5 == 0 or i == total - 1:
                    await progress.update(15 + int(60 * (i + 1) / total), f"Removing watermark (frame {i+1}/{total})...")
        if progress.is_cancelled():
            raise asyncio.CancelledError()
        await progress.update(80, "Rebuilding video...")
        await _rebuild_video(job_dir, output_path, fps, input_path, has_audio, encoding_args)
        await progress.update(95, "Finalizing...")
        logger.info("Frame pipeline complete: %s", output_path.name)
    except asyncio.CancelledError:
        logger.info("Frame pipeline cancelled")
        if Path(output_path).exists():
            try: Path(output_path).unlink()
            except Exception: pass
        raise
    finally:
        await manager.remove_dir(job_dir)
        logger.info("Temp frames cleaned: %s", job_dir)

async def process_video_with_lama(**kwargs):
    kwargs.setdefault("processor_name", "lama")
    await process_video_frames(**kwargs)
