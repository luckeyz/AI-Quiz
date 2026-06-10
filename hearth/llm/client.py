"""Chat client for any OpenAI-compatible local server (Ollama, LM Studio,
llama.cpp). Supports tool calling; falls back gracefully when the local
model/server doesn't implement it."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from hearth.config import LLMConfig

log = logging.getLogger(__name__)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResult:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self._http = httpx.AsyncClient(
            base_url=cfg.base_url,
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            timeout=cfg.request_timeout_s,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": messages,
            "max_tokens": max_tokens or self.cfg.max_tokens,
            "temperature": (
                self.cfg.temperature if temperature is None else temperature
            ),
        }
        if tools:
            payload["tools"] = tools

        resp = await self._http.post("/chat/completions", json=payload)
        resp.raise_for_status()
        choice = resp.json()["choices"][0]["message"]

        result = ChatResult(text=choice.get("content") or "")
        for tc in choice.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                log.warning("Model produced unparseable tool args: %r",
                            tc["function"]["arguments"])
                args = {}
            result.tool_calls.append(
                ToolCall(id=tc.get("id", ""), name=tc["function"]["name"],
                         arguments=args)
            )
        return result

    async def summarize(self, text: str, max_tokens: int) -> str:
        """One-shot compression used by the rolling context."""
        result = await self.chat(
            messages=[
                {"role": "system", "content": (
                    "Compress the following conversation transcript into a "
                    "dense factual summary. Preserve: user preferences, "
                    "decisions made, open tasks, names, numbers, and anything "
                    "the assistant promised to do. Omit small talk."
                )},
                {"role": "user", "content": text},
            ],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return result.text.strip()


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars/token) — good enough for budgeting
    a rolling window without shipping a tokenizer per local model."""
    return max(1, len(text) // 4)
