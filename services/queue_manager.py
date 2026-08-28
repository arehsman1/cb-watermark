"""
Processing queue.

V1 enforces a single global job via _global_busy.
V2 only needs to drop that flag to allow concurrent per-user jobs
because jobs are already stored in a dict keyed by user_id.
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class Job:
    """
    Represents one processing task.
    """
    user_id: int
    chat_id: int
    message_id: int
    task_type: str  # 'image' or 'video'
    input_path: Path
    output_path: Path
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)


class QueueManager:
    """
    Thread-safe queue manager.

    Public API:
        is_busy()      -> bool
        start_job()    -> bool  (False if busy)
        cancel_job()   -> bool  (True if job existed and was signalled)
        finish_job()   -> None  (release slot)
        get_job()      -> Optional[Job]
    """

    def __init__(self) -> None:
        self._jobs: dict[int, Job] = {}
        self._global_busy = False
        self._lock = asyncio.Lock()

    async def is_busy(self) -> bool:
        async with self._lock:
            return self._global_busy

    async def start_job(self, job: Job) -> bool:
        async with self._lock:
            if self._global_busy:
                logger.info("Queue busy: rejected job for user %d", job.user_id)
                return False
            self._jobs[job.user_id] = job
            self._global_busy = True
            logger.info("Job started for user %d (%s)", job.user_id, job.task_type)
            return True

    async def cancel_job(self, user_id: int) -> bool:
        async with self._lock:
            job = self._jobs.get(user_id)
            if job is None:
                return False
            job.cancel_event.set()
            logger.info("Cancellation requested for user %d", user_id)
            return True

    async def finish_job(self, user_id: int) -> None:
        async with self._lock:
            job = self._jobs.pop(user_id, None)
            if job:
                self._global_busy = False
                logger.info("Job finished for user %d", user_id)
            else:
                logger.warning("finish_job called for unknown user %d", user_id)

    async def get_job(self, user_id: int) -> Optional[Job]:
        async with self._lock:
            return self._jobs.get(user_id)
