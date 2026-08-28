"""Image: removal then new watermark + compression."""
import asyncio
import shutil
import time
from pathlib import Path
from PIL import Image
from logger import get_logger
from processors.image_compression import get_save_kwargs
from processors.removal.media_processor import media_processor
from services.watermark_service import WatermarkService
from settings_manager import get_orientation, settings
from utilities.progress_tracker import ProgressTracker
logger = get_logger(__name__)

async def process_image(input_path, output_path, watermark_service, progress):
    start_time = time.monotonic()
    try:
        await progress.update(5, "Loading image...")
        img = await asyncio.to_thread(Image.open, input_path)
        if progress.is_cancelled():
            raise asyncio.CancelledError()
        original_ext = input_path.suffix.lower()
        if original_ext in (".jpg", ".jpeg"):
            target_format = "JPEG"
        elif original_ext == ".png":
            target_format = "PNG"
        elif original_ext == ".webp":
            target_format = "WEBP"
        else:
            target_format = img.format or "JPEG"
        orientation = get_orientation(img.width, img.height)
        compression = await settings.get_compression(orientation)
        wm_path = await watermark_service.prepare_watermark(img.width, img.height)
        has_watermark = wm_path is not None and wm_path.exists()
        removal_enabled = await settings.get_removal_enabled(orientation)
        if not has_watermark and not removal_enabled and compression == "original":
            await progress.update(50, "Copying original...")
            await asyncio.to_thread(shutil.copy, input_path, output_path)
            await progress.update(100)
            return
        if progress.is_cancelled():
            raise asyncio.CancelledError()
        if removal_enabled:
            await progress.update(10, "Removing old watermark...")
            if progress.is_cancelled():
                raise asyncio.CancelledError()
            rpos = await settings.get_removal_position(orientation)
            rsize = await settings.get_removal_size(orientation)
            img = await media_processor.remove_watermark_from_image(img, rpos, rsize)
        if progress.is_cancelled():
            raise asyncio.CancelledError()
        await progress.update(15, "Preparing watermark...")
        position = await watermark_service.get_position(orientation)
        if has_watermark:
            await progress.update(30, "Applying watermark...")
            if progress.is_cancelled():
                raise asyncio.CancelledError()
            def _apply():
                base = img.convert("RGBA")
                with Image.open(wm_path) as wm:
                    x, y = watermark_service.calculate_position(position, wm.size, base.size)
                    base.paste(wm, (x, y), wm)
                return base
            img = await asyncio.to_thread(_apply)
            if target_format == "JPEG" and img.mode == "RGBA":
                def _flatten():
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    bg.paste(img, mask=img.getchannel("A"))
                    return bg
                img = await asyncio.to_thread(_flatten)
        if progress.is_cancelled():
            raise asyncio.CancelledError()
        await progress.update(60, "Saving...")
        save_kwargs = await get_save_kwargs(target_format, orientation)
        if "exif" in img.info:
            save_kwargs["exif"] = img.info["exif"]
        def _save():
            img.save(output_path, format=target_format, **save_kwargs)
        await asyncio.to_thread(_save)
        await progress.update(100)
        logger.info("Image saved %s %.2fs", output_path.name, time.monotonic() - start_time)
    except asyncio.CancelledError:
        logger.info("Image cancelled")
        if Path(output_path).exists():
            try: Path(output_path).unlink()
            except Exception: pass
        raise
    except Exception as exc:
        logger.error("Image failed: %s", exc, exc_info=True)
        if Path(output_path).exists():
            try: Path(output_path).unlink()
            except Exception: pass
        raise
