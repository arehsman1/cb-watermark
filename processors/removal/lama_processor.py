"""LaMa AI inpainting — optional, CPU-only."""
from __future__ import annotations
import asyncio
import contextlib
import gc
import importlib.util
from PIL import Image
from logger import get_logger
from processors.removal.base_processor import BaseProcessor
from processors.removal.yolo_detector import build_binary_mask
logger = get_logger(__name__)

class LamaProcessor(BaseProcessor):
    name = "lama"
    def __init__(self):
        self._session_model = None
    def is_available(self):
        return (
            importlib.util.find_spec("simple_lama_inpainting") is not None
            and importlib.util.find_spec("torch") is not None
        )
    @contextlib.asynccontextmanager
    async def loaded_session(self):
        if not self.is_available():
            raise RuntimeError("LaMa not installed. pip install -r requirements-lama.txt")
        def _load():
            import torch
            from simple_lama_inpainting import SimpleLama
            logger.info("LaMa loading (CPU)...")
            return SimpleLama(device=torch.device("cpu"))
        model = await asyncio.to_thread(_load)
        self._session_model = model
        logger.info("LaMa batch session started")
        try:
            yield self
        finally:
            self._session_model = None
            del model
            gc.collect()
            logger.info("LaMa batch session released")
    async def remove(self, image, region):
        if not self.is_available():
            raise RuntimeError("LaMa not installed")
        def _run():
            import torch
            from simple_lama_inpainting import SimpleLama
            has_alpha = image.mode in ("RGBA", "LA")
            alpha = image.getchannel("A") if has_alpha else None
            rgb = image.convert("RGB")
            mask = Image.fromarray(build_binary_mask(rgb.height, rgb.width, region))
            if self._session_model is not None:
                result = self._session_model(rgb, mask)
            else:
                logger.info("LaMa single-call load")
                lama = SimpleLama(device=torch.device("cpu"))
                try:
                    result = lama(rgb, mask)
                finally:
                    del lama
                    gc.collect()
            if has_alpha:
                result = result.convert("RGBA")
                result.putalpha(alpha)
            return result
        try:
            result = await asyncio.to_thread(_run)
            logger.info("LaMa inpainted %s", region)
            return result
        except Exception as exc:
            logger.error("LaMa failed: %s", exc)
            raise
