"""
Async-safe settings manager.

Settings are split into two profiles, "landscape" and "portrait".
Each profile holds its own position/opacity/compression/removal
settings, and is shared between images AND videos of that
orientation (a landscape photo and a landscape video use the same
profile; portrait media of any aspect ratio uses the other one).
The watermark image itself is shared across both orientations.

Encapsulates all JSON persistence so handlers and processors never
touch the filesystem directly. Uses aiofiles to avoid blocking the
event loop during I/O.
"""

import json
from pathlib import Path
from typing import Any, Literal

import aiofiles

from config import SETTINGS_FILE, WATERMARK_FILE, DEFAULT_POSITION, DEFAULT_OPACITY, DEFAULT_COMPRESSION
from logger import get_logger

logger = get_logger(__name__)

Orientation = Literal["landscape", "portrait"]
ORIENTATIONS: tuple[Orientation, ...] = ("landscape", "portrait")

DEFAULT_PROFILE: dict[str, Any] = {
    "position": DEFAULT_POSITION,
    "opacity": DEFAULT_OPACITY,
    "compression": DEFAULT_COMPRESSION,
    "removal_enabled": False,
    "removal_position": "bottom-right",
    "removal_size": "medium",
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "watermark_path": str(WATERMARK_FILE),
    "landscape": dict(DEFAULT_PROFILE),
    "portrait": dict(DEFAULT_PROFILE),
}


def get_orientation(width: int, height: int) -> Orientation:
    """Landscape if wider than tall (or square); portrait otherwise."""
    return "portrait" if height > width else "landscape"


class SettingsManager:
    """
    Manages bot settings stored in a JSON file.

    This class is intentionally simple now so that later migration to
    a database (SQLite/PostgreSQL) only requires swapping the
    internal storage mechanism without changing the public API.
    """

    def __init__(self, file_path: Path = SETTINGS_FILE) -> None:
        self._file = file_path
        self._cache: dict[str, Any] | None = None

    async def _ensure_exists(self) -> None:
        """Create the settings file with defaults if it does not exist."""
        if not self._file.exists():
            logger.info("Settings file not found; creating defaults at %s", self._file)
            await self._write(DEFAULT_SETTINGS)

    @staticmethod
    def _migrate(data: dict[str, Any]) -> dict[str, Any]:
        """
        Upgrade an old flat settings.json (single global profile) to
        the landscape/portrait structure, seeding both profiles with
        whatever the old flat values were.
        """
        if "landscape" in data and "portrait" in data:
            return data

        flat_profile = {
            "position": data.get("position", DEFAULT_POSITION),
            "opacity": data.get("opacity", DEFAULT_OPACITY),
            "compression": data.get("compression", DEFAULT_COMPRESSION),
            "removal_enabled": data.get("removal_enabled", False),
            "removal_position": data.get("removal_position", "bottom-right"),
            "removal_size": data.get("removal_size", "medium"),
        }
        migrated = {
            "watermark_path": data.get("watermark_path", str(WATERMARK_FILE)),
            "landscape": dict(flat_profile),
            "portrait": dict(flat_profile),
        }
        logger.info("Migrated settings.json to landscape/portrait profiles.")
        return migrated

    async def _read(self) -> dict[str, Any]:
        """Read settings from disk. Uses a simple in-memory cache."""
        if self._cache is not None:
            return self._cache

        await self._ensure_exists()
        try:
            async with aiofiles.open(self._file, mode="r", encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Failed to read settings (%s). Using defaults.", exc)
            data = json.loads(json.dumps(DEFAULT_SETTINGS))
            await self._write(data)
            self._cache = data
            return data

        data = self._migrate(data)
        self._cache = data
        return data

    async def _write(self, data: dict[str, Any]) -> None:
        """Atomically write settings to disk and update cache."""
        try:
            async with aiofiles.open(self._file, mode="w", encoding="utf-8") as f:
                await f.write(json.dumps(data, indent=2, ensure_ascii=False))
            self._cache = data
        except Exception as exc:
            logger.error("Failed to write settings: %s", exc)
            raise

    # ── Generic access ───────────────────────────────────────────────

    async def get(self, key: str, default: Any = None) -> Any:
        """Get a top-level (non-profile) setting by key."""
        data = await self._read()
        return data.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        """Set a top-level (non-profile) setting by key."""
        data = await self._read()
        data[key] = value
        await self._write(data)
        logger.info("Setting updated: %s = %s", key, value)

    async def _get_profile_value(self, orientation: Orientation, key: str, default: Any) -> Any:
        data = await self._read()
        profile = data.get(orientation, dict(DEFAULT_PROFILE))
        return profile.get(key, default)

    async def _set_profile_value(self, orientation: Orientation, key: str, value: Any) -> None:
        data = await self._read()
        profile = data.setdefault(orientation, dict(DEFAULT_PROFILE))
        profile[key] = value
        await self._write(data)
        logger.info("Setting updated: %s.%s = %s", orientation, key, value)

    # ── Watermark image (shared across both orientations) ──────────────

    async def get_watermark_path(self) -> Path:
        path_str = await self.get("watermark_path", str(WATERMARK_FILE))
        return Path(path_str)

    async def set_watermark_path(self, path: Path) -> None:
        await self.set("watermark_path", str(path))

    # ── Per-orientation profile settings ────────────────────────────────

    async def get_position(self, orientation: Orientation) -> str:
        return await self._get_profile_value(orientation, "position", DEFAULT_POSITION)

    async def set_position(self, orientation: Orientation, position: str) -> None:
        await self._set_profile_value(orientation, "position", position)

    async def get_opacity(self, orientation: Orientation) -> float:
        return await self._get_profile_value(orientation, "opacity", DEFAULT_OPACITY)

    async def set_opacity(self, orientation: Orientation, opacity: float) -> None:
        await self._set_profile_value(orientation, "opacity", opacity)

    async def get_compression(self, orientation: Orientation) -> str:
        return await self._get_profile_value(orientation, "compression", DEFAULT_COMPRESSION)

    async def set_compression(self, orientation: Orientation, quality: str) -> None:
        await self._set_profile_value(orientation, "compression", quality)

    async def get_removal_enabled(self, orientation: Orientation) -> bool:
        return await self._get_profile_value(orientation, "removal_enabled", False)

    async def set_removal_enabled(self, orientation: Orientation, enabled: bool) -> None:
        await self._set_profile_value(orientation, "removal_enabled", enabled)

    async def get_removal_position(self, orientation: Orientation) -> str:
        return await self._get_profile_value(orientation, "removal_position", "bottom-right")

    async def set_removal_position(self, orientation: Orientation, position: str) -> None:
        await self._set_profile_value(orientation, "removal_position", position)

    async def get_removal_size(self, orientation: Orientation) -> str:
        return await self._get_profile_value(orientation, "removal_size", "medium")

    async def set_removal_size(self, orientation: Orientation, size: str) -> None:
        await self._set_profile_value(orientation, "removal_size", size)

    async def reset_to_defaults(self) -> None:
        """Reset all settings to factory defaults."""
        await self._write(json.loads(json.dumps(DEFAULT_SETTINGS)))
        logger.info("Settings reset to defaults.")


# Singleton instance used across the application
settings = SettingsManager()
