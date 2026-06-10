"""Background job manager. Voice turns must never block on real work, so
anything slow becomes a Job: it runs as an asyncio task, and completion or
failure is reported back through a single event callback that the agent
turns into speech."""

from __future__ import annotations

import asyncio
import itertools
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Coroutine

log = logging.getLogger(__name__)

EventCallback = Callable[[str], Awaitable[None]]


@dataclass
class Job:
    id: str
    description: str
    started: float = field(default_factory=time.time)
    task: asyncio.Task | None = None
    result: str | None = None
    error: str | None = None

    @property
    def status(self) -> str:
        if self.task and not self.task.done():
            return "running"
        return "failed" if self.error else "done"


class JobManager:
    def __init__(self, on_event: EventCallback):
        self._jobs: dict[str, Job] = {}
        self._ids = itertools.count(1)
        self._on_event = on_event

    def submit(self, description: str,
               coro: Coroutine[None, None, str]) -> Job:
        job = Job(id=f"job-{next(self._ids)}", description=description)
        job.task = asyncio.create_task(self._run(job, coro))
        self._jobs[job.id] = job
        log.info("%s started: %s", job.id, description)
        return job

    async def _run(self, job: Job, coro: Coroutine[None, None, str]) -> None:
        try:
            job.result = await coro
            event = (f"Background job '{job.description}' ({job.id}) "
                     f"finished successfully. Result: {job.result[:1500]}")
        except Exception as exc:
            job.error = str(exc)
            log.exception("%s failed", job.id)
            event = (f"Background job '{job.description}' ({job.id}) "
                     f"FAILED: {job.error[:500]}")
        await self._on_event(event)

    def describe_all(self) -> str:
        if not self._jobs:
            return "No jobs have been started."
        lines = []
        for job in self._jobs.values():
            mins = (time.time() - job.started) / 60
            lines.append(f"{job.id} [{job.status}] ({mins:.0f}m) "
                         f"{job.description}")
        return "\n".join(lines)

    async def shutdown(self) -> None:
        for job in self._jobs.values():
            if job.task and not job.task.done():
                job.task.cancel()
