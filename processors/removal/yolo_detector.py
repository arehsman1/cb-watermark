"""Local YOLO watermark detector. On-device only."""
from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Optional
import numpy as np
from PIL import Image
from config import (
    WATERMARK_CLASS_ID, WATERMARK_CONFIDENCE, WATERMARK_MASK_PADDING, WATERMARK_MODEL_PATH,
)
from logger import get_logger
logger = get_logger(__name__)
_model = None
_model_load_attempted = False
_model_available = False

def _clamp_bbox(x, y, w, h, media_w, media_h):
    x = max(0, min(x, media_w - 1))
    y = max(0, min(y, media_h - 1))
    w = max(1, min(w, media_w - x))
    h = max(1, min(h, media_h - y))
    return (x, y, w, h)

def apply_mask_padding(x, y, w, h, media_w, media_h, padding=None):
    pad = WATERMARK_MASK_PADDING if padding is None else padding
    return _clamp_bbox(x - pad, y - pad, w + 2 * pad, h + 2 * pad, media_w, media_h)

def build_binary_mask(media_h, media_w, region):
    mask = np.zeros((media_h, media_w), dtype=np.uint8)
    x, y, w, h = region
    mask[y:y + h, x:x + w] = 255
    return mask

def is_model_available():
    global _model_load_attempted, _model_available
    if _model_load_attempted:
        return _model_available
    return Path(WATERMARK_MODEL_PATH).is_file()

def _load_model():
    global _model, _model_load_attempted, _model_available
    if _model is not None:
        return _model
    _model_load_attempted = True
    path = Path(WATERMARK_MODEL_PATH)
    if not path.is_file():
        logger.error("YOLO model not found at %s — edge fallback will be used.", path)
        _model_available = False
        return None
    try:
        from ultralytics import YOLO
        _model = YOLO(str(path))
        _model_available = True
        logger.info("YOLO model loaded from %s", path)
        return _model
    except Exception as exc:
        logger.error("YOLO load failed: %s", exc)
        _model_available = False
        return None

def _run_inference(image_rgb):
    model = _load_model()
    if model is None:
        return None
    media_h, media_w = image_rgb.shape[:2]
    results = model.predict(source=image_rgb, conf=0.01, verbose=False)
    if not results or results[0].boxes is None or len(results[0].boxes) == 0:
        logger.info("YOLO found zero detections.")
        return None
    boxes = results[0].boxes
    best, best_conf = None, -1.0
    for i in range(len(boxes)):
        cls_id = int(boxes.cls[i].item())
        conf = float(boxes.conf[i].item())
        x1, y1, x2, y2 = [float(v) for v in boxes.xyxy[i].cpu().numpy()]
        if cls_id != WATERMARK_CLASS_ID or conf < WATERMARK_CONFIDENCE:
            continue
        x, y = int(round(x1)), int(round(y1))
        w, h = int(round(x2 - x1)), int(round(y2 - y1))
        x, y, w, h = _clamp_bbox(x, y, w, h, media_w, media_h)
        if conf > best_conf:
            best_conf, best = conf, (x, y, w, h, conf)
    if best is None:
        logger.info("No detection matched class_id=%d conf>=%.2f", WATERMARK_CLASS_ID, WATERMARK_CONFIDENCE)
        return None
    x, y, w, h, conf = best
    logger.info("YOLO selected conf=%.3f bbox=(%d,%d,%d,%d)", conf, x, y, w, h)
    return best

async def detect_yolo_pil(image: Image.Image):
    def _d():
        rgb = np.array(image.convert("RGB"))
        h, w = rgb.shape[:2]
        hit = _run_inference(rgb)
        if hit is None:
            return None
        x, y, bw, bh, _ = hit
        return apply_mask_padding(x, y, bw, bh, w, h)
    return await asyncio.to_thread(_d)

async def detect_yolo_bgr(frame_bgr: np.ndarray):
    def _d():
        import cv2
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        hit = _run_inference(rgb)
        if hit is None:
            return None
        x, y, bw, bh, _ = hit
        return apply_mask_padding(x, y, bw, bh, w, h)
    return await asyncio.to_thread(_d)
