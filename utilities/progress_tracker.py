"""
Progress tracking for a single Telegram message.

Updates are rate-limited to avoid Telegram API throttling.
Cancellation is coordinated through an asyncio.Event shared with the
QueueManager so processors can poll it safely.
"""

import asyncio
import time
from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from logger import get_logger

logger = get_logger(__name__)


class ProgressTracker:
    """
    Manages one progress message.

    *min_interval* controls how often Telegram is hit (default 2.5 s).
    A jump of >= 20 % also triggers an immediate update so the user
    sees meaningful motion.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        message_id: int,
        cancel_event: asyncio.Event,
        min_interval: float = 2.5,
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._message_id = message_id
        self._cancel_event = cancel_event
        self._min_interval = min_interval

        self._start_time = time.monotonic()
        self._last_update = 0.0
        self._last_percent = 0.0

    # ── Cancellation ──────────────────────────────────────────────────

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        self._cancel_event.set()

    # ── Telegram updates ──────────────────────────────────────────────

    async def update(self, percent: float, status: str = "Processing...") -> None:
        """Edit the progress message if enough time has elapsed."""
        percent = max(0.0, min(100.0, percent))
        now = time.monotonic()

        significant_jump = abs(percent - self._last_percent) >= 20
        is_finished = percent >= 100

        if (
            not significant_jump
            and not is_finished
            and (now - self._last_update) < self._min_interval
        ):
            return

        self._last_update = now
        self._last_percent = percent

        bar = self._render_bar(percent)
        eta = self._calculate_eta(percent)

        text = (
            f"⏳ {status}\n\n"
            f"{bar} {percent:.0f}%\n\n"
            f"⏱️ {eta}\n\n"
            f"❌ Press the button below to cancel"
        )

        keyboard: Optional[InlineKeyboardMarkup] = None
        if percent < 100:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_processing")]
                ]
            )

        try:
            await self._bot.edit_message_text(
                chat_id=self._chat_id,
                message_id=self._message_id,
                text=text,
                reply_markup=keyboard,
            )
        except Exception as exc:
            # Ignore "message not modified" or network blips
            logger.debug("Progress update failed: %s", exc)

    async def complete(self) -> None:
        """Show completion text and remove the inline keyboard."""
        text = "✅ Complete!\n\nUploading your file..."
        try:
            await self._bot.edit_message_text(
                chat_id=self._chat_id,
                message_id=self._message_id,
                text=text,
                reply_markup=None,  # Remove cancel button
            )
        except Exception as exc:
            logger.debug("Complete message failed: %s", exc)

    async def fail(self, reason: str) -> None:
        """Show failure text and remove the inline keyboard."""
        text = f"❌ Processing failed.\n\nReason: {reason}\n\nPress ⬅️ Back to return to the menu."
        try:
            await self._bot.edit_message_text(
                chat_id=self._chat_id,
                message_id=self._message_id,
                text=text,
                reply_markup=None,  # Remove cancel button
            )
        except Exception as exc:
            logger.debug("Fail message failed: %s", exc)

    # ── Formatting helpers ────────────────────────────────────────────

    def _render_bar(self, percent: float, width: int = 12) -> str:
        filled = int(width * percent / 100)
        return "█" * filled + "░" * (width - filled)

    def _calculate_eta(self, percent: float) -> str:
        if percent <= 1.0:
            return "ETA: calculating..."

        elapsed = time.monotonic() - self._start_time
        total_estimated = elapsed / (percent / 100.0)
        remaining = total_estimated - elapsed

        if remaining <= 0:
            return "ETA: almost done..."
        if remaining < 60:
            return f"ETA: {int(remaining)} seconds"
        return f"ETA: {int(remaining // 60)}m {int(remaining % 60)}s"
