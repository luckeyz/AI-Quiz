"""The never-ending context.

A live window of recent turns is kept under a hard token budget. When the
budget is exceeded, everything except the most recent `roll_keep_turns`
turns is compressed by the LLM into a summary block, written to durable
memory, and dropped from the window. The window thus "resets" continuously
and the conversation has no maximum length.

Tool-call message pairs are kept intact across rolls so the model never
sees an orphaned tool result.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from hearth.config import ContextConfig
from hearth.context.memory import MemoryStore
from hearth.llm.client import LLMClient, estimate_tokens

log = logging.getLogger(__name__)


class RollingContext:
    def __init__(self, cfg: ContextConfig, llm: LLMClient,
                 memory: MemoryStore, persona: str):
        self.cfg = cfg
        self.llm = llm
        self.memory = memory
        self.persona = persona
        self._turns: list[dict[str, Any]] = []
        self._roll_lock = asyncio.Lock()

    # -- building the prompt -------------------------------------------------

    def messages(self) -> list[dict[str, Any]]:
        system = self.persona
        preamble = self.memory.memory_preamble()
        if preamble:
            system += "\n\n" + preamble
        return [{"role": "system", "content": system}, *self._turns]

    # -- appending turns ------------------------------------------------------

    def add_user(self, text: str) -> None:
        self._turns.append({"role": "user", "content": text})

    def add_assistant(self, text: str,
                      tool_calls: list[dict[str, Any]] | None = None) -> None:
        msg: dict[str, Any] = {"role": "assistant", "content": text}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self._turns.append(msg)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        self._turns.append({"role": "tool", "tool_call_id": tool_call_id,
                            "content": content})

    def add_event(self, text: str) -> None:
        """Out-of-band events (job finished, call reconnected) enter the
        conversation as system notes so the agent can voice them."""
        self._turns.append({"role": "system", "content": f"[event] {text}"})

    # -- the roll -------------------------------------------------------------

    def _window_tokens(self) -> int:
        return sum(estimate_tokens(str(m.get("content") or "")) +
                   estimate_tokens(str(m.get("tool_calls") or ""))
                   for m in self._turns)

    async def maybe_roll(self) -> None:
        if self._window_tokens() <= self.cfg.window_token_budget:
            return
        async with self._roll_lock:
            if self._window_tokens() <= self.cfg.window_token_budget:
                return
            await self._roll()

    async def _roll(self) -> None:
        keep = self.cfg.roll_keep_turns
        cut = max(0, len(self._turns) - keep)
        # Never split an assistant tool_call from its tool results.
        while cut > 0 and self._turns[cut].get("role") == "tool":
            cut -= 1
        if cut == 0:
            return

        old, recent = self._turns[:cut], self._turns[cut:]
        transcript = "\n".join(
            f"{m['role']}: {m.get('content') or m.get('tool_calls')}"
            for m in old
        )
        log.info("Rolling context: compressing %d turns (%d kept)",
                 len(old), len(recent))
        try:
            summary = await self.llm.summarize(
                transcript, self.cfg.summary_max_tokens)
        except Exception:
            # If summarization fails, drop the oldest half rather than die —
            # staying alive matters more than perfect recall.
            log.exception("Summarization failed; dropping oldest turns")
            self._turns = recent
            return

        self.memory.append_summary(summary)
        self._turns = recent
