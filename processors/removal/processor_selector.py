"""Automatic OpenCV vs LaMa selection."""
from PIL import Image
from logger import get_logger
from processors.removal.complexity_analyzer import analyze_complexity
from processors.removal.lama_processor import LamaProcessor
from processors.removal.opencv_processor import OpenCVProcessor
logger = get_logger(__name__)

class ProcessorSelector:
    def __init__(self):
        self._opencv = OpenCVProcessor()
        self._lama = LamaProcessor()
    def analyze(self, image, region):
        import numpy as np
        x, y, w, h = region
        if w <= 0 or h <= 0:
            return {"edge_density": 0.0, "laplacian_variance": 0.0, "is_complex": False}
        gray = np.array(image.convert("L").crop((x, y, x + w, y + h)))
        return analyze_complexity(gray)
    def select(self, complexity):
        if complexity.get("is_complex") and self._lama.is_available():
            return self._lama
        return self._opencv
    async def remove(self, image, region):
        complexity = self.analyze(image, region)
        processor = self.select(complexity)
        logger.info(
            "complexity edge=%.3f lap=%.1f complex=%s -> %s (lama=%s)",
            complexity.get("edge_density", 0), complexity.get("laplacian_variance", 0),
            complexity.get("is_complex"), processor.name, self._lama.is_available(),
        )
        try:
            return await processor.remove(image, region), processor.name
        except Exception as exc:
            if processor.name == "opencv":
                raise
            logger.warning("LaMa failed (%s); OpenCV fallback", exc)
            return await self._opencv.remove(image, region), "opencv (fallback)"
