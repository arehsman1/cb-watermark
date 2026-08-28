from abc import ABC, abstractmethod
from PIL import Image

class BaseProcessor(ABC):
    name: str = "base"
    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError
    @abstractmethod
    async def remove(self, image: Image.Image, region: tuple) -> Image.Image:
        """Real inpainting only — never blur or simple overlay."""
        raise NotImplementedError
