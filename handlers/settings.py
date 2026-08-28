"""
Settings menu handlers.

Structure:
  ⚙️ Settings
    ├── 🖼️ Set Watermark        (shared across both orientations)
    ├── 📐 Landscape Settings   ─┐
    └── 📱 Portrait Settings    ─┴─> 📍 Position / 🌫️ Opacity /
                                     🗜️ Compression / 🧹 Old Watermark Removal

Landscape and portrait each have their own independent profile,
shared between images and videos of that orientation. Which profile
a given "Position"/"Opacity"/etc. button edits is tracked via FSM
data (state.update_data(orientation=...)), not the state name itself,
since Position/Opacity/etc. are reused for both orientations.
"""

import asyncio
import shutil
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from config import WATERMARK_DIR, WATERMARK_FILE
from keyboards.main_menu import main_menu_kb
from keyboards.settings_menu import settings_menu_kb
from keyboards.orientation_menu import orientation_menu_kb
from keyboards.position_menu import position_menu_kb
from keyboards.opacity_menu import opacity_menu_kb
from keyboards.compression_menu import compression_menu_kb
from keyboards.removal_menu import removal_menu_kb
from keyboards.removal_size_menu import removal_size_menu_kb
from logger import get_logger
from settings_manager import settings
from states import BotStates
from utilities.file_manager import FileManager

logger = get_logger(__name__)
router = Router()

ORIENTATION_LABELS = {"landscape": "📐 Landscape", "portrait": "📱 Portrait"}


async def _get_orientation(state: FSMContext) -> str:
    """Read which orientation profile is currently being edited."""
    data = await state.get_data()
    return data.get("orientation", "landscape")


# ── Settings menu entry ─────────────────────────────────────────────

@router.message(F.text == "⚙️ Settings")
async def open_settings(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.settings)
    await message.answer("⚙️ Settings", reply_markup=settings_menu_kb())


# ── Watermark upload (shared across both orientations) ────────────────

@router.message(F.text == "🖼️ Set Watermark")
async def request_watermark(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.waiting_watermark)
    await message.answer(
        "Please send a PNG image with transparency to use as your watermark.\n\n"
        "It will replace any existing watermark automatically, and is used for "
        "both Landscape and Portrait media.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="⬅️ Back")]],
            resize_keyboard=True,
        ),
    )


@router.message(BotStates.waiting_watermark, F.document)
async def receive_watermark_document(
    message: Message, state: FSMContext, bot: Bot, file_manager: FileManager
) -> None:
    """Accept a PNG document and replace the stored watermark."""
    if message.document.mime_type != "image/png":
        await message.answer("❌ Watermark must be a PNG file.")
        return

    temp_path: Path | None = None
    try:
        file_info = await bot.get_file(message.document.file_id)
        temp_path = file_manager.generate_unique_path(WATERMARK_DIR, ".png")
        await bot.download_file(file_info.file_path, temp_path)

        # Validate PNG and transparency
        from PIL import Image

        with Image.open(temp_path) as img:
            if img.mode not in ("RGBA", "P", "LA"):
                await message.answer(
                    "❌ Watermark should have transparency. "
                    "Please send a PNG with an alpha channel."
                )
                return
            if img.mode == "P" and "transparency" not in img.info:
                await message.answer(
                    "❌ Watermark should have transparency. "
                    "Please send a PNG with an alpha channel."
                )
                return

        # Atomically replace existing watermark
        await file_manager.remove(WATERMARK_FILE)
        await asyncio.to_thread(shutil.move, str(temp_path), str(WATERMARK_FILE))
        await settings.set_watermark_path(WATERMARK_FILE)

        await state.set_state(BotStates.settings)
        await message.answer(
            "✅ Watermark updated successfully!", reply_markup=settings_menu_kb()
        )
    except Exception as exc:
        logger.error("Watermark upload failed: %s", exc)
        await state.set_state(BotStates.settings)
        await message.answer(
            "❌ Failed to process watermark. Please try again.",
            reply_markup=settings_menu_kb(),
        )
    finally:
        if temp_path and temp_path.exists():
            await file_manager.remove(temp_path)


@router.message(BotStates.waiting_watermark, F.photo)
async def reject_watermark_photo(message: Message, state: FSMContext) -> None:
    await message.answer(
        "❌ Please send the watermark as a file (not a compressed photo) "
        "to preserve transparency."
    )


# ── Orientation picker ──────────────────────────────────────────────────

@router.message(F.text == "📐 Landscape Settings")
async def open_landscape_settings(message: Message, state: FSMContext) -> None:
    await state.update_data(orientation="landscape")
    await state.set_state(BotStates.orientation_settings)
    await message.answer(
        "📐 Landscape Settings\n\nApplies to both landscape images and landscape "
        "videos.",
        reply_markup=orientation_menu_kb(),
    )


@router.message(F.text == "📱 Portrait Settings")
async def open_portrait_settings(message: Message, state: FSMContext) -> None:
    await state.update_data(orientation="portrait")
    await state.set_state(BotStates.orientation_settings)
    await message.answer(
        "📱 Portrait Settings\n\nApplies to both portrait images and portrait "
        "videos, regardless of exact size (9:16, 4:5, 3:4, etc.).",
        reply_markup=orientation_menu_kb(),
    )


# ── Position submenu ──────────────────────────────────────────────────

@router.message(F.text == "📍 Watermark Position")
async def open_position(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.position)
    orientation = await _get_orientation(state)
    await message.answer(
        f"📍 Select watermark position ({ORIENTATION_LABELS[orientation]}):",
        reply_markup=position_menu_kb(),
    )


@router.message(
    BotStates.position,
    F.text.in_(
        {"↖️ Top Left", "↗️ Top Right", "↙️ Bottom Left", "↘️ Bottom Right", "🎯 Center"}
    ),
)
async def set_position(message: Message, state: FSMContext) -> None:
    mapping = {
        "↖️ Top Left": "top-left",
        "↗️ Top Right": "top-right",
        "↙️ Bottom Left": "bottom-left",
        "↘️ Bottom Right": "bottom-right",
        "🎯 Center": "center",
    }
    orientation = await _get_orientation(state)
    pos = mapping[message.text]
    await settings.set_position(orientation, pos)
    await state.set_state(BotStates.orientation_settings)
    await message.answer(
        f"✅ {ORIENTATION_LABELS[orientation]} position set to {message.text}",
        reply_markup=orientation_menu_kb(),
    )


# ── Opacity submenu ───────────────────────────────────────────────────

@router.message(F.text == "🌫️ Watermark Opacity")
async def open_opacity(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.opacity)
    orientation = await _get_orientation(state)
    await message.answer(
        f"🌫️ Select watermark opacity ({ORIENTATION_LABELS[orientation]}):",
        reply_markup=opacity_menu_kb(),
    )


@router.message(BotStates.opacity, F.text.in_({"100%", "80%", "60%", "40%", "20%"}))
async def set_opacity(message: Message, state: FSMContext) -> None:
    mapping = {
        "100%": 1.0,
        "80%": 0.8,
        "60%": 0.6,
        "40%": 0.4,
        "20%": 0.2,
    }
    orientation = await _get_orientation(state)
    opacity = mapping[message.text]
    await settings.set_opacity(orientation, opacity)
    await state.set_state(BotStates.orientation_settings)
    await message.answer(
        f"✅ {ORIENTATION_LABELS[orientation]} opacity set to {message.text}",
        reply_markup=orientation_menu_kb(),
    )


# ── Compression submenu ───────────────────────────────────────────────

@router.message(F.text == "🗜️ Compression Quality")
async def open_compression(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.compression)
    orientation = await _get_orientation(state)
    await message.answer(
        f"🗜️ Select compression quality ({ORIENTATION_LABELS[orientation]}):",
        reply_markup=compression_menu_kb(),
    )


@router.message(
    BotStates.compression,
    F.text.in_(
        {"⭐ Original (No Compression)", "⭐⭐ High Quality", "⭐⭐⭐ Medium Quality"}
    ),
)
async def set_compression(message: Message, state: FSMContext) -> None:
    mapping = {
        "⭐ Original (No Compression)": "original",
        "⭐⭐ High Quality": "high",
        "⭐⭐⭐ Medium Quality": "medium",
    }
    orientation = await _get_orientation(state)
    quality = mapping[message.text]
    await settings.set_compression(orientation, quality)
    await state.set_state(BotStates.orientation_settings)
    await message.answer(
        f"✅ {ORIENTATION_LABELS[orientation]} compression set to {message.text}",
        reply_markup=orientation_menu_kb(),
    )


# ── Old watermark removal submenu ──────────────────────────────────────

@router.message(F.text == "🧹 Old Watermark Removal")
async def open_removal(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.removal)
    orientation = await _get_orientation(state)
    enabled = await settings.get_removal_enabled(orientation)
    status = "🟢 ON" if enabled else "🔴 OFF"
    await message.answer(
        f"🧹 Old Watermark Removal ({ORIENTATION_LABELS[orientation]}): {status}\n\n"
        "When enabled, the bot analyzes the corner of each upload for an "
        "existing watermark and attempts to erase it before adding yours. "
        "This is a best-effort reconstruction, results vary with the "
        "background behind the old watermark.",
        reply_markup=removal_menu_kb(),
    )


@router.message(F.text == "🟢 Enable Removal")
async def enable_removal(message: Message, state: FSMContext) -> None:
    orientation = await _get_orientation(state)
    await settings.set_removal_enabled(orientation, True)
    await message.answer(
        f"✅ Old watermark removal enabled for {ORIENTATION_LABELS[orientation]}.",
        reply_markup=removal_menu_kb(),
    )


@router.message(F.text == "🔴 Disable Removal")
async def disable_removal(message: Message, state: FSMContext) -> None:
    orientation = await _get_orientation(state)
    await settings.set_removal_enabled(orientation, False)
    await message.answer(
        f"✅ Old watermark removal disabled for {ORIENTATION_LABELS[orientation]}.",
        reply_markup=removal_menu_kb(),
    )


@router.message(F.text == "📍 Removal Position")
async def open_removal_position(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.removal_position)
    await message.answer(
        "📍 Which corner is the OLD watermark usually in?",
        reply_markup=position_menu_kb(),
    )


@router.message(
    BotStates.removal_position,
    F.text.in_(
        {"↖️ Top Left", "↗️ Top Right", "↙️ Bottom Left", "↘️ Bottom Right", "🎯 Center"}
    ),
)
async def set_removal_position(message: Message, state: FSMContext) -> None:
    mapping = {
        "↖️ Top Left": "top-left",
        "↗️ Top Right": "top-right",
        "↙️ Bottom Left": "bottom-left",
        "↘️ Bottom Right": "bottom-right",
        "🎯 Center": "center",
    }
    orientation = await _get_orientation(state)
    pos = mapping[message.text]
    await settings.set_removal_position(orientation, pos)
    await state.set_state(BotStates.removal)
    await message.answer(
        f"✅ Removal position set to {message.text}", reply_markup=removal_menu_kb()
    )


@router.message(F.text == "📏 Search Area Size")
async def open_removal_size(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.removal_size)
    await message.answer(
        "📏 How large an area should the bot search for the old watermark? "
        "Bigger isn't always better, too large can eat into real image content.",
        reply_markup=removal_size_menu_kb(),
    )


@router.message(
    BotStates.removal_size,
    F.text.in_({"🔹 Small (~20%)", "🔸 Medium (~30%)", "🔶 Large (~40%)"}),
)
async def set_removal_size(message: Message, state: FSMContext) -> None:
    mapping = {
        "🔹 Small (~20%)": "small",
        "🔸 Medium (~30%)": "medium",
        "🔶 Large (~40%)": "large",
    }
    orientation = await _get_orientation(state)
    size = mapping[message.text]
    await settings.set_removal_size(orientation, size)
    await state.set_state(BotStates.removal)
    await message.answer(
        f"✅ Search area set to {message.text}", reply_markup=removal_menu_kb()
    )


# ── Back navigation ───────────────────────────────────────────────────

@router.message(F.text == "⬅️ Back")
async def handle_back(message: Message, state: FSMContext) -> None:
    current = await state.get_state()

    if current is None:
        await message.answer("Main menu:", reply_markup=main_menu_kb())
        return

    if current in (BotStates.settings.state, BotStates.waiting_watermark.state):
        await state.clear()
        await message.answer("Main menu:", reply_markup=main_menu_kb())
    elif current == BotStates.orientation_settings.state:
        await state.set_state(BotStates.settings)
        await message.answer("⚙️ Settings", reply_markup=settings_menu_kb())
    elif current in (
        BotStates.position.state,
        BotStates.opacity.state,
        BotStates.compression.state,
        BotStates.removal.state,
    ):
        await state.set_state(BotStates.orientation_settings)
        orientation = await _get_orientation(state)
        await message.answer(
            f"{ORIENTATION_LABELS[orientation]} Settings",
            reply_markup=orientation_menu_kb(),
        )
    elif current in (
        BotStates.removal_position.state,
        BotStates.removal_size.state,
    ):
        await state.set_state(BotStates.removal)
        await message.answer("🧹 Old Watermark Removal", reply_markup=removal_menu_kb())
