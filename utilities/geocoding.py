"""
GPS reverse geocoding.

Uses OpenStreetMap's Nominatim service — free, no API key or paid
service required. Nominatim's usage policy requires a descriptive
User-Agent and caps requests at ~1/sec; both are respected here.

Reverse geocoding is best-effort: any failure (network, timeout, rate
limit, no result) returns None rather than raising, since a location
lookup failing should never block viewing the rest of an image's
metadata.
"""

from typing import Optional

import httpx

from logger import get_logger

logger = get_logger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "BrandingBot/1.0 (Telegram watermarking bot; contact via bot owner)"
TIMEOUT_SECONDS = 5.0


async def reverse_geocode(latitude: float, longitude: float) -> Optional[str]:
    """Return a human-readable address for (latitude, longitude), or None on any failure."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.get(
                NOMINATIM_URL,
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "format": "json",
                    "zoom": 16,
                    "addressdetails": 0,
                },
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()
            address = data.get("display_name")
            return address
    except Exception as exc:
        logger.warning("Reverse geocoding failed for (%s, %s): %s", latitude, longitude, exc)
        return None
