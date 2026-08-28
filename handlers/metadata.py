"""
Metadata Tools handlers.

Flow:
  📋 Metadata Tools -> send file (as document, to preserve original bytes)
    -> 👁️ View / ✏️ Edit / 🗑️ Clear
       Edit -> pick field -> type new value -> updated file sent back

Images use utilities/image_metadata.py (Pillow EXIF, incl. GPS
sub-IFD, reverse-geocoded via utilities/geocoding.py). Videos use
utilities/video_metadata.py (ffprobe/ffmpeg, stream-copy only — never
re-encodes just to touch metadata).
"""

import asyncio
from pathlib import Path
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext

from config import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    METADATA_MAX_IMAGE_SIZE,
    METADATA_MAX_VIDEO_SIZE,
    METADATA_MAX_VIDEO_DURATION,
    METADATA_MAX_VIDEO_WIDTH,
    METADATA_MAX_VIDEO_HEIGHT,
    TEMP_DIR,
)
from keyboards.main_menu import main_menu_kb
from keyboards.metadata_menu import metadata_menu_kb
from keyboards.metadata_edit_menu import (
    IMAGE_EDIT_FIELD_LABELS,
    VIDEO_EDIT_FIELD_LABELS,
    image_edit_field_menu_kb,
    video_edit_field_menu_kb,
)
from logger import get_logger
from states import BotStates
from utilities.file_manager import FileManager, file_manager as default_file_manager
from utilities.geocoding import reverse_geocode
from utilities.image_metadata import (
    clear_image_metadata,
    read_image_metadata,
    write_image_metadata,
)
from utilities.video_metadata import (
    clear_video_metadata,
    read_video_metadata,
    write_video_metadata,
)

logger = get_logger(__name__)
router = Router()


# ── Entry point ──────────────────────────────────────────────────────

@router.message(F.text == "📋 Metadata Tools")
async def open_metadata_tools(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.waiting_metadata_file)
    await message.answer(
        "📋 Metadata Tools\n\n"
        "Send a photo or video as a *file* (not a compressed photo) to view, "
        "edit, or clear its metadata.\n\n"
        f"Images: JPG, JPEG, PNG, WEBP — up to {METADATA_MAX_IMAGE_SIZE // (1024*1024)}MB\n"
        f"Video: MP4, MOV, AVI, MKV — up to {METADATA_MAX_VIDEO_SIZE // (1024*1024)}MB, "
        f"under {int(METADATA_MAX_VIDEO_DURATION // 60)} min, up to "
        f"{METADATA_MAX_VIDEO_WIDTH}x{METADATA_MAX_VIDEO_HEIGHT}",
        parse_mode="Markdown",
    )


@router.message(BotStates.waiting_metadata_file, F.photo)
async def reject_compressed_photo(message: Message) -> None:
    await message.answer(
        "❌ Please send it as a file (not a compressed photo) — Telegram strips "
        "metadata from compressed photos, which defeats the purpose here."
    )


async def _probe_video_limits(path: Path) -> Optional[str]:
    """Return an error message if the video exceeds metadata-tools limits, else None."""
    from utilities.video_metadata import probe_raw

    try:
        info = await probe_raw(path)
    except Exception as exc:
        return f"Could not read video: {exc}"

    fmt = info.get("format", {})
    duration = float(fmt.get("duration", 0) or 0)
    if duration > METADATA_MAX_VIDEO_DURATION:
        return f"Video is too long (max {int(METADATA_MAX_VIDEO_DURATION // 60)} minutes)."

    video_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if video_stream:
        w, h = video_stream.get("width", 0), video_stream.get("height", 0)
        if w > METADATA_MAX_VIDEO_WIDTH or h > METADATA_MAX_VIDEO_HEIGHT:
            return f"Video resolution too high (max {METADATA_MAX_VIDEO_WIDTH}x{METADATA_MAX_VIDEO_HEIGHT})."
    return None


@router.message(BotStates.waiting_metadata_file, F.document)
async def receive_metadata_file(
    message: Message, state: FSMContext, bot: Bot, file_manager: FileManager
) -> None:
    doc = message.document
    filename = doc.file_name or "file"
    suffix = Path(filename).suffix.lower()

    if suffix in IMAGE_EXTENSIONS:
        file_type = "image"
        max_size = METADATA_MAX_IMAGE_SIZE
    elif suffix in VIDEO_EXTENSIONS:
        file_type = "video"
        max_size = METADATA_MAX_VIDEO_SIZE
    else:
        await message.answer(
            "❌ Unsupported file type. Send JPG/JPEG/PNG/WEBP for images, "
            "or MP4/MOV/AVI/MKV for video."
        )
        return

    if doc.file_size and doc.file_size > max_size:
        await message.answer(f"❌ File too large (max {max_size // (1024*1024)}MB for this type).")
        return

    temp_path = file_manager.generate_unique_path(TEMP_DIR, suffix)
    try:
        file_info = await bot.get_file(doc.file_id)
        await bot.download_file(file_info.file_path, temp_path)
    except Exception as exc:
        logger.error("Metadata file download failed: %s", exc)
        await message.answer("❌ Failed to download the file. Please try again.")
        return

    ok, error = await file_manager.validate_upload(
        temp_path,
        IMAGE_EXTENSIONS if file_type == "image" else VIDEO_EXTENSIONS,
        max_size=max_size,
    )
    if not ok:
        await message.answer(f"❌ {error}")
        await file_manager.remove(temp_path)
        return

    if file_type == "image":
        ok, error = file_manager.check_image_pixel_limit(temp_path)
        if not ok:
            await message.answer(f"❌ {error}")
            await file_manager.remove(temp_path)
            return

    if file_type == "video":
        limit_error = await _probe_video_limits(temp_path)
        if limit_error:
            await message.answer(f"❌ {limit_error}")
            await file_manager.remove(temp_path)
            return

    await state.update_data(
        metadata_file_path=str(temp_path),
        metadata_file_type=file_type,
        metadata_original_name=filename,
    )
    await state.set_state(BotStates.metadata_menu)
    await message.answer(
        f"✅ Got it — {filename}\n\nWhat would you like to do?",
        reply_markup=metadata_menu_kb(),
    )


# ── View ─────────────────────────────────────────────────────────────

def _format_image_metadata(meta: dict, address: Optional[str]) -> str:
    lines = ["📋 *Image Metadata*\n"]

    fi = meta.get("file_info", {})
    lines.append("*File Information*")
    lines.append(f"• Name: {fi.get('name')}")
    lines.append(f"• Format: {fi.get('format')}")
    lines.append(f"• Size: {fi.get('size_bytes', 0) / 1024:.1f} KB")
    lines.append(f"• Dimensions: {fi.get('width')}x{fi.get('height')}")

    if camera := meta.get("camera"):
        lines.append("\n*Camera Information*")
        labels = {
            "manufacturer": "Manufacturer",
            "model": "Model",
            "lens": "Lens",
            "focal_length": "Focal Length",
            "aperture": "Aperture",
            "iso": "ISO",
            "shutter_speed": "Shutter Speed",
            "flash": "Flash",
        }
        for key, label in labels.items():
            if key in camera:
                lines.append(f"• {label}: {camera[key]}")

    if dates := meta.get("dates"):
        lines.append("\n*Date Information*")
        labels = {"date_taken": "Date Taken", "date_created": "Date Created", "date_modified": "Date Modified"}
        for key, label in labels.items():
            if key in dates:
                lines.append(f"• {label}: {dates[key]}")

    if software := meta.get("software"):
        lines.append("\n*Software*")
        if "editing_software" in software:
            lines.append(f"• Editing Software: {software['editing_software']}")

    if copyright_info := meta.get("copyright"):
        lines.append("\n*Copyright*")
        if "owner" in copyright_info:
            lines.append(f"• Copyright Owner: {copyright_info['owner']}")
        if "artist" in copyright_info:
            lines.append(f"• Artist: {copyright_info['artist']}")

    if gps := meta.get("gps"):
        lines.append("\n*GPS Information*")
        lines.append(f"• Latitude: {gps.get('latitude')}")
        lines.append(f"• Longitude: {gps.get('longitude')}")
        if "altitude_m" in gps:
            lines.append(f"• Altitude: {gps['altitude_m']:.1f}m")
        if "timestamp" in gps:
            lines.append(f"• GPS Timestamp: {gps['timestamp']}")
        if address:
            lines.append(f"• Location: {address}")

    if len(lines) == 5:  # only file_info was ever added
        lines.append("\n_No EXIF metadata found in this image._")

    return "\n".join(lines)


def _format_video_metadata(meta: dict) -> str:
    lines = ["📋 *Video Metadata*\n"]

    fi = meta.get("file_info", {})
    lines.append("*File Information*")
    lines.append(f"• Name: {fi.get('name')}")
    lines.append(f"• Format: {fi.get('format')}")
    lines.append(f"• Size: {fi.get('size_bytes', 0) / (1024*1024):.1f} MB")
    lines.append(f"• Duration: {fi.get('duration')}")
    lines.append(f"• Resolution: {fi.get('width')}x{fi.get('height')}")
    lines.append(f"• Codec: {fi.get('codec')}")

    if tags := meta.get("tags"):
        lines.append("\n*Tags*")
        for key, value in tags.items():
            lines.append(f"• {key.title()}: {value}")
    else:
        lines.append("\n_No container metadata tags found in this video._")

    return "\n".join(lines)


@router.message(BotStates.metadata_menu, F.text == "👁️ View Metadata")
async def view_metadata(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    path = Path(data["metadata_file_path"])
    file_type = data["metadata_file_type"]

    await message.answer("⏳ Reading metadata...")

    try:
        if file_type == "image":
            meta = await asyncio.to_thread(read_image_metadata, path)
            address = None
            if gps := meta.get("gps"):
                address = await reverse_geocode(gps["latitude"], gps["longitude"])
            text = _format_image_metadata(meta, address)
        else:
            meta = await read_video_metadata(path)
            text = _format_video_metadata(meta)
    except Exception as exc:
        logger.error("Metadata read failed: %s", exc)
        await message.answer("❌ Failed to read metadata from this file.")
        return

    logger.info(
        "Metadata viewed: user=%d file_type=%s", message.from_user.id, file_type
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=metadata_menu_kb())


# ── Clear ────────────────────────────────────────────────────────────

@router.message(BotStates.metadata_menu, F.text == "🗑️ Clear Metadata")
async def clear_metadata(
    message: Message, state: FSMContext, file_manager: FileManager
) -> None:
    data = await state.get_data()
    path = Path(data["metadata_file_path"])
    file_type = data["metadata_file_type"]
    original_name = data["metadata_original_name"]

    await message.answer("⏳ Clearing metadata...")

    output_path = file_manager.generate_unique_path(TEMP_DIR, path.suffix)
    try:
        if file_type == "image":
            await asyncio.to_thread(clear_image_metadata, path, output_path)
        else:
            await clear_video_metadata(path, output_path)

        await message.answer_document(
            FSInputFile(output_path, filename=f"cleared_{original_name}"),
            caption="✅ Metadata cleared.",
        )
        logger.info(
            "Metadata cleared: user=%d file_type=%s", message.from_user.id, file_type
        )
    except Exception as exc:
        logger.error("Metadata clear failed: %s", exc)
        await message.answer("❌ Failed to clear metadata from this file.")
    finally:
        await file_manager.remove(output_path)


# ── Edit ─────────────────────────────────────────────────────────────

@router.message(BotStates.metadata_menu, F.text == "✏️ Edit Metadata")
async def open_edit_menu(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    file_type = data["metadata_file_type"]
    await state.set_state(BotStates.metadata_edit_field)
    kb = image_edit_field_menu_kb() if file_type == "image" else video_edit_field_menu_kb()
    await message.answer("✏️ Which field would you like to edit?", reply_markup=kb)


@router.message(
    BotStates.metadata_edit_field,
    F.text.in_(set(IMAGE_EDIT_FIELD_LABELS) | set(VIDEO_EDIT_FIELD_LABELS)),
)
async def pick_edit_field(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    file_type = data["metadata_file_type"]
    labels = IMAGE_EDIT_FIELD_LABELS if file_type == "image" else VIDEO_EDIT_FIELD_LABELS

    if message.text not in labels:
        return  # belongs to the other file type's menu, ignore

    field = labels[message.text]
    await state.update_data(metadata_edit_field=field, metadata_edit_label=message.text)
    await state.set_state(BotStates.metadata_edit_value)
    await message.answer(f"Send the new value for *{message.text}*:", parse_mode="Markdown")


@router.message(BotStates.metadata_edit_value, F.text, ~F.text.in_({"⬅️ Back"}))
async def apply_edit(
    message: Message, state: FSMContext, file_manager: FileManager
) -> None:
    data = await state.get_data()
    path = Path(data["metadata_file_path"])
    file_type = data["metadata_file_type"]
    field = data["metadata_edit_field"]
    label = data["metadata_edit_label"]
    original_name = data["metadata_original_name"]
    new_value = message.text.strip()

    await message.answer("⏳ Applying edit...")

    output_path = file_manager.generate_unique_path(TEMP_DIR, path.suffix)
    try:
        if file_type == "image":
            await asyncio.to_thread(write_image_metadata, path, output_path, {field: new_value})
        else:
            await write_video_metadata(path, output_path, {field: new_value})

        # The edited file becomes the new working copy, so further
        # edits/view/clear in this session build on top of it.
        await file_manager.remove(path)
        await state.update_data(metadata_file_path=str(output_path))

        await message.answer_document(
            FSInputFile(output_path, filename=f"edited_{original_name}"),
            caption=f"✅ {label} updated.",
        )
        logger.info(
            "Metadata edited: user=%d file_type=%s field=%s",
            message.from_user.id,
            file_type,
            field,
        )
    except Exception as exc:
        logger.error("Metadata edit failed: %s", exc)
        await message.answer("❌ Failed to apply that edit.")
        await file_manager.remove(output_path)
        await state.set_state(BotStates.metadata_menu)
        await message.answer("What next?", reply_markup=metadata_menu_kb())
        return

    await state.set_state(BotStates.metadata_menu)
    await message.answer("What next?", reply_markup=metadata_menu_kb())


# ── Back navigation (state-specific, takes precedence over the ─────────
# ── generic handler in handlers/settings.py since this router is ──────
# ── registered first) ───────────────────────────────────────────────

@router.message(BotStates.waiting_metadata_file, F.text == "⬅️ Back")
async def back_from_waiting_file(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Main menu:", reply_markup=main_menu_kb())


@router.message(BotStates.metadata_menu, F.text == "⬅️ Back")
async def back_from_metadata_menu(
    message: Message, state: FSMContext, file_manager: FileManager
) -> None:
    data = await state.get_data()
    if path_str := data.get("metadata_file_path"):
        await file_manager.remove(Path(path_str))
    await state.clear()
    await message.answer("Main menu:", reply_markup=main_menu_kb())


@router.message(BotStates.metadata_edit_field, F.text == "⬅️ Back")
async def back_from_edit_field(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.metadata_menu)
    await message.answer("What next?", reply_markup=metadata_menu_kb())


@router.message(BotStates.metadata_edit_value, F.text == "⬅️ Back")
async def back_from_edit_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    file_type = data["metadata_file_type"]
    await state.set_state(BotStates.metadata_edit_field)
    kb = image_edit_field_menu_kb() if file_type == "image" else video_edit_field_menu_kb()
    await message.answer("✏️ Which field would you like to edit?", reply_markup=kb)
