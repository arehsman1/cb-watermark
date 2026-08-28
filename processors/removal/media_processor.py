"""Single entry for watermark removal."""
from logger import get_logger
from processors.removal.processor_selector import ProcessorSelector
from processors.removal.yolo_detector import detect_yolo_bgr, detect_yolo_pil
from processors.watermark_removal import (
    build_delogo_filter, detect_watermark_region, detect_watermark_region_cv,
)
logger = get_logger(__name__)

class MediaProcessor:
    def __init__(self):
        self._selector = ProcessorSelector()
    async def _resolve_region_image(self, image, position, search_size):
        r = await detect_yolo_pil(image)
        if r is not None:
            logger.info("Image detection source=YOLO region=%s", r)
            return r
        logger.warning("YOLO miss/unavailable; edge fallback pos=%s size=%s", position, search_size)
        r = await detect_watermark_region(image, position, search_size)
        logger.info("Image detection source=edge-fallback region=%s", r)
        return r
    async def _resolve_region_frame(self, frame_bgr, position, search_size):
        r = await detect_yolo_bgr(frame_bgr)
        if r is not None:
            logger.info("Video detection source=YOLO region=%s", r)
            return r
        logger.warning("YOLO miss/unavailable; edge fallback pos=%s size=%s", position, search_size)
        r = await detect_watermark_region_cv(frame_bgr, position, search_size)
        logger.info("Video detection source=edge-fallback region=%s", r)
        return r
    async def remove_watermark_from_image(self, image, position, search_size):
        region = await self._resolve_region_image(image, position, search_size)
        result, used = await self._selector.remove(image, region)
        logger.info("Image removal done processor=%s region=%s", used, region)
        return result
    async def detect_video_region(self, frame_bgr, position, search_size):
        return await self._resolve_region_frame(frame_bgr, position, search_size)
    async def select_video_processor(self, frame_bgr, region):
        import cv2
        from PIL import Image
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        complexity = self._selector.analyze(img, region)
        return self._selector.select(complexity).name, complexity
    async def build_video_removal_filter(self, region):
        return build_delogo_filter(region)
    def new_lama_processor(self):
        from processors.removal.lama_processor import LamaProcessor
        return LamaProcessor()
    def new_opencv_processor(self):
        from processors.removal.opencv_processor import OpenCVProcessor
        return OpenCVProcessor()

media_processor = MediaProcessor()
