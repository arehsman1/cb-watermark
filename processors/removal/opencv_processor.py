import asyncio
import numpy as np
from PIL import Image
from config import OPENCV_INPAINT_RADIUS
from logger import get_logger
from processors.removal.base_processor import BaseProcessor
from processors.removal.yolo_detector import build_binary_mask
logger = get_logger(__name__)

class OpenCVProcessor(BaseProcessor):
    name = "opencv"
    def is_available(self) -> bool:
        return True
    async def remove(self, image, region):
        def _inpaint():
            import cv2
            x, y, w, h = region
            has_alpha = image.mode in ("RGBA", "LA")
            alpha = image.getchannel("A") if has_alpha else None
            rgb = np.array(image.convert("RGB"))
            mh, mw = rgb.shape[:2]
            mask = build_binary_mask(mh, mw, (x, y, w, h))
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            out = cv2.inpaint(bgr, mask, inpaintRadius=OPENCV_INPAINT_RADIUS, flags=cv2.INPAINT_TELEA)
            result = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
            if has_alpha:
                result = result.convert("RGBA")
                result.putalpha(alpha)
            logger.info("OpenCV Telea region=(%d,%d,%d,%d) r=%d", x, y, w, h, OPENCV_INPAINT_RADIUS)
            return result
        return await asyncio.to_thread(_inpaint)
