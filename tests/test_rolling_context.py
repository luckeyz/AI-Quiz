"""Tests for the never-ending context. Run with: pytest
(requires the package's deps installed: pip install -e .)
"""

import asyncio

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("pydantic")

from hearth.config import ContextConfig  # noqa: E402
from hearth.context.memory import MemoryStore  # noqa: E402
from hearth.context.rolling import RollingContext  # noqa: E402


class FakeLLM:
    def __init__(self):
        self.summarize_calls = 0

    async def summarize(self, text: str, max_tokens: int) -> str:
        self.summarize_calls += 1
        return f"summary#{self.summarize_calls}"


@pytest.fixture
def ctx(tmp_path):
    cfg = ContextConfig(window_token_budget=100, roll_keep_turns=4,
                        memory_dir=tmp_path)
    llm = FakeLLM()
    memory = MemoryStore(tmp_path)
    return RollingContext(cfg, llm, memory, persona="test persona"), llm, memory


def test_roll_compresses_old_turns_into_memory(ctx):
    rolling, llm, memory = ctx
    for i in range(30):
        rolling.add_user(f"user message number {i} with some padding text")
        rolling.add_assistant(f"assistant reply number {i} with padding")

    asyncio.run(rolling.maybe_roll())

    assert llm.summarize_calls == 1
    assert len(rolling._turns) == 4  # roll_keep_turns survive verbatim
    assert memory.recent_summaries() == ["summary#1"]
    # The summary is injected into the system prompt of the next call.
    assert "summary#1" in rolling.messages()[0]["content"]


def test_no_roll_under_budget(ctx):
    rolling, llm, _ = ctx
    rolling.add_user("hi")
    rolling.add_assistant("hello")
    asyncio.run(rolling.maybe_roll())
    assert llm.summarize_calls == 0
    assert len(rolling._turns) == 2


def test_roll_never_orphans_tool_results(ctx):
    rolling, _, _ = ctx
    for i in range(20):
        rolling.add_user(f"padding user turn {i} {'x' * 40}")
    rolling.add_assistant("", tool_calls=[{"id": "t1", "type": "function",
                                           "function": {"name": "f",
                                                        "arguments": "{}"}}])
    rolling.add_tool_result("t1", "result")
    rolling.add_assistant("done")
    rolling.add_user("thanks")

    asyncio.run(rolling.maybe_roll())

    roles = [m["role"] for m in rolling._turns]
    if "tool" in roles:
        # the tool result's assistant tool_call must still precede it
        idx = roles.index("tool")
        assert rolling._turns[idx - 1].get("tool_calls")


def test_pinned_facts_persist(tmp_path):
    memory = MemoryStore(tmp_path)
    memory.pin("user_name", "Alex")
    reloaded = MemoryStore(tmp_path)
    assert "Alex" in reloaded.memory_preamble()
