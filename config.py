"""
Centralized configuration for the Branding Bot.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    print("FATAL: BOT_TOKEN is not set. Export it in the environment or .env file.")
    sys.exit(1)

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

BASE_DIR: Path = Path(__file__).parent.resolve()
UPLOADS_DIR: Path = BASE_DIR / "uploads"
OUTPUTS_DIR: Path = BASE_DIR / "outputs"
TEMP_DIR: Path = BASE_DIR / "temp"
WATERMARK_DIR: Path = BASE_DIR / "watermark"
LOGS_DIR: Path = BASE_DIR / "logs"
MODELS_DIR: Path = BASE_DIR / "models"

for _dir in (UPLOADS_DIR, OUTPUTS_DIR, TEMP_DIR, WATERMARK_DIR, LOGS_DIR, MODELS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE: Path = BASE_DIR / "settings.json"
WATERMARK_FILE: Path = WATERMARK_DIR / "logo.png"

MAX_INPUT_SIZE: int = 45 * 1024 * 1024
MAX_OUTPUT_SIZE: int = 50 * 1024 * 1024
TELEGRAM_DOWNLOAD_TIMEOUT: int = 120
TELEGRAM_UPLOAD_TIMEOUT: int = 120

DEFAULT_POSITION: str = "bottom-right"
DEFAULT_OPACITY: float = 0.8
DEFAULT_COMPRESSION: str = "original"

METADATA_MAX_IMAGE_SIZE: int = 20 * 1024 * 1024
METADATA_MAX_VIDEO_SIZE: int = 200 * 1024 * 1024
METADATA_MAX_VIDEO_DURATION: float = 10 * 60
METADATA_MAX_VIDEO_WIDTH: int = 1920
METADATA_MAX_VIDEO_HEIGHT: int = 1080
MAX_IMAGE_PIXELS: int = 64_000_000

IMAGE_MIME_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp"}
IMAGE_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_MIME_TYPES: set[str] = {
    "video/mp4", "video/quicktime", "video/x-msvideo", "video/x-matroska",
}
VIDEO_EXTENSIONS: set[str] = {".mp4", ".mov", ".avi", ".mkv"}

WATERMARK_MODEL_PATH: Path = Path(
    os.getenv("WATERMARK_MODEL_PATH", str(MODELS_DIR / "watermark_detector.pt"))
)
WATERMARK_CLASS_ID: int = int(os.getenv("WATERMARK_CLASS_ID", "0"))
WATERMARK_CONFIDENCE: float = float(os.getenv("WATERMARK_CONFIDENCE", "0.25"))
WATERMARK_MASK_PADDING: int = int(os.getenv("WATERMARK_MASK_PADDING", "3"))
OPENCV_INPAINT_RADIUS: int = int(os.getenv("OPENCV_INPAINT_RADIUS", "3"))
VIDEO_REDETECT_INTERVAL: int = int(os.getenv("VIDEO_REDETECT_INTERVAL", "0"))

EDGE_DENSITY_THRESHOLD: float = float(os.getenv("EDGE_DENSITY_THRESHOLD", "0.12"))
LAPLACIAN_VARIANCE_THRESHOLD: float = float(
    os.getenv("LAPLACIAN_VARIANCE_THRESHOLD", "500.0")
)

MAX_LAMA_VIDEO_FRAMES: int = int(os.getenv("MAX_LAMA_VIDEO_FRAMES", "300"))
MAX_OPENCV_VIDEO_FRAMES: int = int(os.getenv("MAX_OPENCV_VIDEO_FRAMES", "900"))
