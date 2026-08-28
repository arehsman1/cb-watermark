"""
Image EXIF metadata: read, write, clear.

Uses Pillow's built-in Exif class (Image.getexif()) rather than a
separate library like piexif — it's already a dependency of this
project, and Pillow 10.x's Exif class supports the sub-IFDs (Exif
detail tags, GPS) needed here across JPEG, PNG, and WEBP.

EXIF tag reference (standard numeric IDs):
  IFD0 (top level):     Make, Model, Software, DateTime, Artist, Copyright
  Exif sub-IFD (0x8769): DateTimeOriginal, DateTimeDigitized, ExposureTime,
                         FNumber, ISOSpeedRatings, FocalLength, Flash, LensModel
  GPS sub-IFD (0x8825): GPSLatitude, GPSLongitude, GPSAltitude, GPSTimeStamp, etc.
"""

from pathlib import Path
from typing import Any, Optional

from PIL import Image

# IFD0 tags
TAG_MAKE = 0x010F
TAG_MODEL = 0x0110
TAG_SOFTWARE = 0x0131
TAG_DATETIME = 0x0132  # "modified" date
TAG_ARTIST = 0x013B
TAG_COPYRIGHT = 0x8298

# Exif sub-IFD tag (pointer) and its own tags
EXIF_IFD_POINTER = 0x8769
TAG_DATETIME_ORIGINAL = 0x9003  # "date taken"
TAG_DATETIME_DIGITIZED = 0x9004  # "date created"
TAG_EXPOSURE_TIME = 0x829A  # shutter speed
TAG_FNUMBER = 0x829D  # aperture
TAG_ISO = 0x8827
TAG_FOCAL_LENGTH = 0x920A
TAG_FLASH = 0x9209
TAG_LENS_MODEL = 0xA434

# GPS sub-IFD tag (pointer) and its own tags
GPS_IFD_POINTER = 0x8825
GPS_LAT_REF = 0x0001
GPS_LAT = 0x0002
GPS_LON_REF = 0x0003
GPS_LON = 0x0004
GPS_ALT_REF = 0x0005
GPS_ALT = 0x0006
GPS_TIMESTAMP = 0x0007
GPS_DATESTAMP = 0x001D

FLASH_LABELS = {
    0x0: "No Flash",
    0x1: "Flash Fired",
    0x5: "Flash Fired, Return not detected",
    0x7: "Flash Fired, Return detected",
    0x9: "Flash Fired, Compulsory",
    0x10: "Flash did not fire, Compulsory",
    0x18: "Flash did not fire, Auto mode",
    0x19: "Flash Fired, Auto mode",
    0x20: "No flash function",
    0x41: "Flash Fired, Red-eye reduction",
}


def _rational_to_float(value: Any) -> Optional[float]:
    """Pillow represents EXIF rationals as IFDRational or (num, denom) tuples."""
    try:
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            return float(value.numerator) / float(value.denominator) if value.denominator else None
        if isinstance(value, tuple) and len(value) == 2:
            return float(value[0]) / float(value[1]) if value[1] else None
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _dms_to_decimal(dms: tuple, ref: str) -> Optional[float]:
    """Convert EXIF GPS (degrees, minutes, seconds) + hemisphere ref to decimal degrees."""
    try:
        degrees = _rational_to_float(dms[0]) or 0.0
        minutes = _rational_to_float(dms[1]) or 0.0
        seconds = _rational_to_float(dms[2]) or 0.0
        decimal = degrees + minutes / 60.0 + seconds / 3600.0
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except (IndexError, TypeError):
        return None


def read_image_metadata(path: Path) -> dict:
    """
    Read all supported metadata categories from an image.

    Returns a dict with keys: file_info, camera, dates, software,
    copyright, gps (gps is omitted entirely if no GPS data exists —
    callers should not render an empty GPS section).
    """
    with Image.open(path) as img:
        file_info = {
            "name": path.name,
            "format": img.format or path.suffix.lstrip(".").upper(),
            "size_bytes": path.stat().st_size,
            "width": img.width,
            "height": img.height,
        }

        exif = img.getexif()
        result: dict = {"file_info": file_info}

        if not exif:
            return result

        camera = {}
        if make := exif.get(TAG_MAKE):
            camera["manufacturer"] = str(make).strip()
        if model := exif.get(TAG_MODEL):
            camera["model"] = str(model).strip()

        exif_sub = exif.get_ifd(EXIF_IFD_POINTER)
        if exif_sub:
            if lens := exif_sub.get(TAG_LENS_MODEL):
                camera["lens"] = str(lens).strip()
            if focal := exif_sub.get(TAG_FOCAL_LENGTH):
                val = _rational_to_float(focal)
                if val is not None:
                    camera["focal_length"] = f"{val:.1f}mm"
            if fnumber := exif_sub.get(TAG_FNUMBER):
                val = _rational_to_float(fnumber)
                if val is not None:
                    camera["aperture"] = f"f/{val:.1f}"
            if iso := exif_sub.get(TAG_ISO):
                camera["iso"] = str(iso)
            if exposure := exif_sub.get(TAG_EXPOSURE_TIME):
                val = _rational_to_float(exposure)
                if val is not None:
                    camera["shutter_speed"] = f"1/{round(1/val)}s" if val < 1 else f"{val:.1f}s"
            if flash := exif_sub.get(TAG_FLASH):
                camera["flash"] = FLASH_LABELS.get(int(flash), f"Unknown ({flash})")

        if camera:
            result["camera"] = camera

        dates = {}
        if exif_sub:
            if dt_orig := exif_sub.get(TAG_DATETIME_ORIGINAL):
                dates["date_taken"] = str(dt_orig)
            if dt_dig := exif_sub.get(TAG_DATETIME_DIGITIZED):
                dates["date_created"] = str(dt_dig)
        if dt_mod := exif.get(TAG_DATETIME):
            dates["date_modified"] = str(dt_mod)
        if dates:
            result["dates"] = dates

        software = {}
        if sw := exif.get(TAG_SOFTWARE):
            software["editing_software"] = str(sw).strip()
        if software:
            result["software"] = software

        copyright_info = {}
        if cr := exif.get(TAG_COPYRIGHT):
            copyright_info["owner"] = str(cr).strip()
        if artist := exif.get(TAG_ARTIST):
            copyright_info["artist"] = str(artist).strip()
        if copyright_info:
            result["copyright"] = copyright_info

        gps_ifd = exif.get_ifd(GPS_IFD_POINTER)
        if gps_ifd:
            gps: dict = {}
            lat_dms, lat_ref = gps_ifd.get(GPS_LAT), gps_ifd.get(GPS_LAT_REF)
            lon_dms, lon_ref = gps_ifd.get(GPS_LON), gps_ifd.get(GPS_LON_REF)
            if lat_dms and lat_ref:
                gps["latitude"] = _dms_to_decimal(lat_dms, lat_ref)
            if lon_dms and lon_ref:
                gps["longitude"] = _dms_to_decimal(lon_dms, lon_ref)
            if alt := gps_ifd.get(GPS_ALT):
                alt_val = _rational_to_float(alt)
                alt_ref = gps_ifd.get(GPS_ALT_REF, 0)
                if alt_val is not None:
                    gps["altitude_m"] = -alt_val if alt_ref == 1 else alt_val
            if ts := gps_ifd.get(GPS_TIMESTAMP):
                try:
                    h, m, s = (int(_rational_to_float(v) or 0) for v in ts)
                    date_stamp = gps_ifd.get(GPS_DATESTAMP, "")
                    gps["timestamp"] = f"{date_stamp} {h:02d}:{m:02d}:{s:02d}".strip()
                except (TypeError, ValueError):
                    pass
            # Only include the section if we actually resolved coordinates
            if "latitude" in gps and "longitude" in gps:
                result["gps"] = gps

        return result


def clear_image_metadata(input_path: Path, output_path: Path) -> None:
    """Re-save the image with no EXIF/metadata at all."""
    with Image.open(input_path) as img:
        # Re-encode from raw pixel data only — no exif kwarg means
        # Pillow writes nothing, regardless of what the source had.
        save_kwargs: dict = {}
        if img.format == "JPEG":
            save_kwargs["quality"] = 95
        img.save(output_path, format=img.format, **save_kwargs)


# Only these are meaningfully user-editable via a chat UI — the rest
# (camera make/model, focal length, etc.) are sensor-reported facts,
# not something a person retypes by hand.
EDITABLE_FIELDS: dict[str, tuple[int, Optional[int]]] = {
    "artist": (TAG_ARTIST, None),
    "copyright": (TAG_COPYRIGHT, None),
    "software": (TAG_SOFTWARE, None),
    "date_modified": (TAG_DATETIME, None),
}


def write_image_metadata(input_path: Path, output_path: Path, updates: dict[str, str]) -> None:
    """
    Apply `updates` (field_name -> new string value, from EDITABLE_FIELDS)
    on top of the image's existing EXIF, and save to output_path.
    """
    with Image.open(input_path) as img:
        exif = img.getexif()
        for field, value in updates.items():
            if field not in EDITABLE_FIELDS:
                continue
            tag, _ = EDITABLE_FIELDS[field]
            exif[tag] = value

        save_kwargs: dict = {"exif": exif}
        if img.format == "JPEG":
            save_kwargs["quality"] = 95
        img.save(output_path, format=img.format, **save_kwargs)
