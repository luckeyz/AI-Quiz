"""Durable long-term memory: append-only JSONL of summary blocks plus a
small set of pinned facts. Survives restarts, so the agent's life on the
machine is continuous even across daemon restarts."""

from __future__ import annotations

import json
import time
from pathlib import Path


class MemoryStore:
    def __init__(self, memory_dir: Path):
        self.dir = memory_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.summaries_path = self.dir / "summaries.jsonl"
        self.pinned_path = self.dir / "pinned.json"

    def append_summary(self, text: str) -> None:
        record = {"ts": time.time(), "summary": text}
        with self.summaries_path.open("a") as f:
            f.write(json.dumps(record) + "\n")

    def recent_summaries(self, n: int = 5) -> list[str]:
        if not self.summaries_path.exists():
            return []
        lines = self.summaries_path.read_text().splitlines()
        return [json.loads(line)["summary"] for line in lines[-n:]]

    def pinned_facts(self) -> dict[str, str]:
        if not self.pinned_path.exists():
            return {}
        return json.loads(self.pinned_path.read_text())

    def pin(self, key: str, value: str) -> None:
        facts = self.pinned_facts()
        facts[key] = value
        self.pinned_path.write_text(json.dumps(facts, indent=2))

    def memory_preamble(self) -> str:
        """Rendered into the system prompt on every LLM call."""
        parts: list[str] = []
        facts = self.pinned_facts()
        if facts:
            parts.append("Pinned facts about the user and environment:\n" +
                         "\n".join(f"- {k}: {v}" for k, v in facts.items()))
        summaries = self.recent_summaries()
        if summaries:
            parts.append("Summaries of earlier conversation (oldest first):\n" +
                         "\n---\n".join(summaries))
        return "\n\n".join(parts)
