"""Agentic harness runner: turns a spoken request into a `claude -p ...`
(or any configured agent CLI) subprocess running inside an isolated
workspace directory. This is how "make me a website" becomes actual files
on disk."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path

from hearth.config import ActionsConfig

log = logging.getLogger(__name__)


class HarnessRunner:
    def __init__(self, cfg: ActionsConfig):
        self.cfg = cfg
        self.cfg.workspace_dir.mkdir(parents=True, exist_ok=True)

    def new_workspace(self, slug_source: str) -> Path:
        slug = re.sub(r"[^a-z0-9]+", "-", slug_source.lower()).strip("-")[:40]
        ws = self.cfg.workspace_dir / f"{int(time.time())}-{slug or 'task'}"
        ws.mkdir(parents=True)
        return ws

    async def run(self, prompt: str, workspace: Path | None = None) -> str:
        """Run the configured agent CLI to completion; returns its output
        plus where the work landed. Long — callers should wrap in a Job."""
        ws = workspace or self.new_workspace(prompt)
        cmd = [part.replace("{prompt}", prompt)
               for part in self.cfg.harness.claude_cmd]

        log.info("Harness in %s: %s", ws, cmd[0])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=ws,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(
                proc.communicate(), timeout=self.cfg.harness.job_timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(
                f"Harness timed out after {self.cfg.harness.job_timeout_s}s "
                f"(workspace: {ws})")

        text = out.decode(errors="replace").strip()
        if proc.returncode != 0:
            raise RuntimeError(
                f"Harness exited {proc.returncode} (workspace: {ws}):\n"
                f"{text[-1000:]}")
        return f"Workspace: {ws}\n{text[-2000:]}"
