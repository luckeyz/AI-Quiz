"""The conversational agent: one brain shared by all channels.

Channels feed it transcribed user turns; it returns spoken replies, runs
tool calls through the action router, and pushes proactive utterances
(job completions) back to whichever channels are live.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from hearth.actions.router import ActionRouter
from hearth.config import Config
from hearth.context.memory import MemoryStore
from hearth.context.rolling import RollingContext
from hearth.llm.client import LLMClient

log = logging.getLogger(__name__)

# A channel registers one of these to receive proactive speech.
Speaker = Callable[[str], Awaitable[None]]

MAX_TOOL_ROUNDS = 6


class Agent:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.llm = LLMClient(cfg.llm)
        self.memory = MemoryStore(cfg.context.memory_dir)
        self.context = RollingContext(
            cfg.context, self.llm, self.memory, cfg.assistant.persona)
        self.router = ActionRouter(cfg, on_job_event=self._on_job_event)
        self._speakers: dict[str, Speaker] = {}
        self._turn_lock = asyncio.Lock()

    # -- channel registration -------------------------------------------------

    def attach_speaker(self, channel_id: str, speaker: Speaker) -> None:
        self._speakers[channel_id] = speaker

    def detach_speaker(self, channel_id: str) -> None:
        self._speakers.pop(channel_id, None)

    async def _broadcast(self, text: str) -> None:
        for speaker in list(self._speakers.values()):
            try:
                await speaker(text)
            except Exception:
                log.exception("Speaker failed; channel will reconnect")

    # -- the turn -------------------------------------------------------------

    async def respond(self, user_text: str) -> str:
        """One user turn in, one spoken reply out. Tool calls happen
        inside the turn; long jobs return immediately with a job id and
        report back later via _on_job_event."""
        async with self._turn_lock:
            self.context.add_user(user_text)
            reply = await self._complete()
            await self.context.maybe_roll()
            return reply

    async def _complete(self) -> str:
        for _ in range(MAX_TOOL_ROUNDS):
            result = await self.llm.chat(
                self.context.messages(), tools=self.router.tool_schemas())

            if not result.tool_calls:
                text = result.text.strip() or "Hm, give me that once more?"
                self.context.add_assistant(text)
                return text

            self.context.add_assistant(
                result.text,
                tool_calls=[
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.name,
                                  "arguments": _json(tc.arguments)}}
                    for tc in result.tool_calls
                ],
            )
            for tc in result.tool_calls:
                outcome = await self.router.dispatch(tc.name, tc.arguments)
                self.context.add_tool_result(tc.id, outcome)

        text = "I started on that, but I'm going in circles — ask me again?"
        self.context.add_assistant(text)
        return text

    # -- proactive speech ------------------------------------------------------

    async def _on_job_event(self, event: str) -> None:
        """Background job finished/failed: voice it on all live channels."""
        self.context.add_event(event)
        try:
            result = await self.llm.chat(self.context.messages())
            line = result.text.strip() or event
        except Exception:
            log.exception("LLM unavailable for job event; speaking raw event")
            line = event
        self.context.add_assistant(line)
        await self._broadcast(line)
        await self.context.maybe_roll()

    async def close(self) -> None:
        await self.router.shutdown()
        await self.llm.close()


def _json(obj: object) -> str:
    import json
    return json.dumps(obj)
