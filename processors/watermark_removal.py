"""Edge-based fallback when YOLO is unavailable."""
from __future__ import annotations
import asyncio
from typing import Optional
import numpy as np
from PIL import Image
from logger import get_logger
logger = get_logger(__name__)
SIZE_FRACTIONS = {"small": 0.20, "medium": 0.30, "large": 0.40}

def _clamp_to_frame(x, y, w, h, media_w, media_h):
    x = max(0, min(x, media_w - 2))
    y = max(0, min(y, media_h - 2))
    w = max(1, min(w, media_w - 1 - x))
    h = max(1, min(h, media_h - 1 - y))
    return (x, y, w, h)

def _crop_bounds(position, search_frac, media_w, media_h):
    sw = max(1, min(media_w, int(media_w * search_frac)))
    sh = max(1, min(media_h, int(media_h * search_frac)))
    positions = {
        "top-left": (0, 0), "top-right": (media_w - sw, 0),
        "bottom-left": (0, media_h - sh), "bottom-right": (media_w - sw, media_h - sh),
        "center": ((media_w - sw) // 2, (media_h - sh) // 2),
    }
    x, y = positions.get(position, positions["bottom-right"])
    return (x, y, sw, sh)

def _find_watermark_bbox(gray_crop):
    import cv2
    if gray_crop.size == 0:
        return None
    edges = cv2.dilate(cv2.Canny(gray_crop, 50, 150), np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    min_area = max(16, int(gray_crop.shape[0] * gray_crop.shape[1] * 0.002))
    valid = [c for c in contours if cv2.contourArea(c) >= min_area]
    if not valid:
        return None
    x0, y0 = gray_crop.shape[1], gray_crop.shape[0]
    x1, y1 = 0, 0
    for c in valid:
        x, y, w, h = cv2.boundingRect(c)
        x0, y0 = min(x0, x), min(y0, y)
        x1, y1 = max(x1, x + w), max(y1, y + h)
    pad = 4
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1 = min(gray_crop.shape[1], x1 + pad)
    y1 = min(gray_crop.shape[0], y1 + pad)
    return (x0, y0, x1 - x0, y1 - y0)

async def detect_watermark_region(img, position, search_key="medium"):
    def _detect():
        media_w, media_h = img.size
        frac = SIZE_FRACTIONS.get(search_key, 0.30)
        cx, cy, cw, ch = _crop_bounds(position, frac, media_w, media_h)
        gray = np.array(img.convert("L").crop((cx, cy, cx + cw, cy + ch)))
        bbox = _find_watermark_bbox(gray)
        if bbox is None:
            return _clamp_to_frame(cx, cy, cw, ch, media_w, media_h)
        bx, by, bw, bh = bbox
        return _clamp_to_frame(cx + bx, cy + by, bw, bh, media_w, media_h)
    return await asyncio.to_thread(_detect)

async def detect_watermark_region_cv(frame_bgr, position, search_key="medium"):
    def _detect():
        import cv2
        media_h, media_w = frame_bgr.shape[:2]
        frac = SIZE_FRACTIONS.get(search_key, 0.30)
        cx, cy, cw, ch = _crop_bounds(position, frac, media_w, media_h)
        gray = cv2.cvtColor(frame_bgr[cy:cy+ch, cx:cx+cw], cv2.COLOR_BGR2GRAY)
        bbox = _find_watermark_bbox(gray)
        if bbox is None:
            return _clamp_to_frame(cx, cy, cw, ch, media_w, media_h)
        bx, by, bw, bh = bbox
        return _clamp_to_frame(cx + bx, cy + by, bw, bh, media_w, media_h)
    return await asyncio.to_thread(_detect)

def build_delogo_filter(region):
    x, y, w, h = region
    return f"delogo=x={x}:y={y}:w={w}:h={h}"
