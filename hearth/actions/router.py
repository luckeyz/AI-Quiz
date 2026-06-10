"""Tool schemas the LLM sees, and the dispatch that makes them real.

Fast actions (email, documents, memory) run inline within the voice turn.
Slow actions (websites, arbitrary agent tasks) become background Jobs and
return immediately with a job id; the agent voices the outcome when the
job finishes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from hearth.actions.builtin.documents import read_document, write_document
from hearth.actions.builtin.email import check_email
from hearth.actions.builtin.website import website_prompt
from hearth.actions.harness import HarnessRunner
from hearth.actions.jobs import EventCallback, JobManager
from hearth.config import Config
from hearth.context.memory import MemoryStore

log = logging.getLogger(__name__)

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "agent_task",
            "description": (
                "Run a long-form task with a full coding/automation agent in "
                "an isolated workspace: write code, research, refactor, "
                "scaffold projects, anything multi-step. Runs in the "
                "background; you'll be told when it finishes."),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string",
                               "description": "Complete instructions for the agent."},
                    "summary": {"type": "string",
                                "description": "Short label for the job, e.g. 'refactor quiz app'."},
                },
                "required": ["prompt", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "make_website",
            "description": ("Build a static website from a description. "
                            "Background job."),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string",
                                    "description": "What the site is for, pages, style."},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_email",
            "description": "List the user's unread email (sender and subject).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_document",
            "description": "Save a document/note as Markdown on disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string",
                                "description": "Full Markdown body."},
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_document",
            "description": "Read back a previously saved document by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string",
                             "description": "Part of the filename or title."},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_jobs",
            "description": "Status of all background jobs this session.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": ("Pin a durable fact about the user or environment "
                            "(name, preferences, recurring details). Persists "
                            "forever across restarts."),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
            },
        },
    },
]


class ActionRouter:
    def __init__(self, cfg: Config, on_job_event: EventCallback):
        self.cfg = cfg
        self.harness = HarnessRunner(cfg.actions)
        self.jobs = JobManager(on_job_event)
        self.memory = MemoryStore(cfg.context.memory_dir)

    def tool_schemas(self) -> list[dict[str, Any]]:
        return TOOL_SCHEMAS

    async def dispatch(self, name: str, args: dict[str, Any]) -> str:
        try:
            return await self._dispatch(name, args)
        except Exception as exc:
            log.exception("Tool %s failed", name)
            return f"Tool error: {exc}"

    async def _dispatch(self, name: str, args: dict[str, Any]) -> str:
        match name:
            case "agent_task":
                job = self.jobs.submit(
                    args["summary"], self.harness.run(args["prompt"]))
                return (f"Started background job {job.id} "
                        f"('{job.description}'). Tell the user it's underway; "
                        "you'll hear when it finishes.")
            case "make_website":
                desc = args["description"]
                job = self.jobs.submit(
                    f"website: {desc[:50]}",
                    self.harness.run(website_prompt(desc)))
                return (f"Started website build as {job.id}. Tell the user "
                        "it's underway.")
            case "check_email":
                return await check_email(self.cfg.actions.email)
            case "write_document":
                return write_document(self.cfg.actions.documents_dir,
                                      args["title"], args["content"])
            case "read_document":
                return read_document(self.cfg.actions.documents_dir,
                                     args["name"])
            case "list_jobs":
                return self.jobs.describe_all()
            case "remember":
                self.memory.pin(args["key"], args["value"])
                return f"Pinned: {args['key']} = {args['value']}"
            case _:
                return f"Unknown tool '{name}'. Available: " + ", ".join(
                    t["function"]["name"] for t in TOOL_SCHEMAS)

    async def shutdown(self) -> None:
        await self.jobs.shutdown()


def _pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2)
