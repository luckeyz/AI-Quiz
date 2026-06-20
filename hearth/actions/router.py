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
from hearth.buddies.store import BuddyStore
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
    {
        "type": "function",
        "function": {
            "name": "pair_buddy",
            "description": ("Register an accountability buddy pairing between "
                            "two users. Both users must agree; use their "
                            "Discord user IDs or display names as identifiers."),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string",
                                "description": "The user initiating the pairing."},
                    "buddy_id": {"type": "string",
                                 "description": "The user to pair with."},
                },
                "required": ["user_id", "buddy_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unpair_buddy",
            "description": "Remove a user's current buddy pairing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buddy_status",
            "description": ("Show a user's buddy, their shared goals (with "
                            "completion status), and any pending notes from "
                            "their buddy."),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_buddy_goal",
            "description": ("Add a shared accountability goal for a buddy pair. "
                            "Both buddies can see and complete each other's goals."),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string",
                                "description": "The user setting the goal."},
                    "goal": {"type": "string",
                             "description": "Description of the goal."},
                },
                "required": ["user_id", "goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_buddy_goal",
            "description": "Mark a shared goal as completed by its index number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "goal_index": {"type": "integer",
                                   "description": "Zero-based index from buddy_status."},
                },
                "required": ["user_id", "goal_index"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "leave_buddy_note",
            "description": ("Leave a note for your buddy to read next time they "
                            "check in. Notes are delivered once and then cleared."),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_user_id": {"type": "string",
                                     "description": "The user leaving the note."},
                    "note": {"type": "string",
                             "description": "The note text."},
                },
                "required": ["from_user_id", "note"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "collect_buddy_notes",
            "description": ("Retrieve and clear all pending notes for a user "
                            "from their buddy. Call this when the user checks in."),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                },
                "required": ["user_id"],
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
        self.buddies = BuddyStore(cfg.context.buddy_dir)

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
            case "pair_buddy":
                return self.buddies.pair(args["user_id"], args["buddy_id"])
            case "unpair_buddy":
                return self.buddies.unpair(args["user_id"])
            case "buddy_status":
                return self.buddies.status_report(args["user_id"])
            case "set_buddy_goal":
                return self.buddies.set_goal(args["user_id"], args["goal"])
            case "complete_buddy_goal":
                return self.buddies.complete_goal(
                    args["user_id"], int(args["goal_index"]))
            case "leave_buddy_note":
                return self.buddies.leave_note(
                    args["from_user_id"], args["note"])
            case "collect_buddy_notes":
                notes = self.buddies.pop_notes(args["user_id"])
                if not notes:
                    return "No pending notes from your buddy."
                lines = [f"Notes for {args['user_id']} from their buddy:"]
                for n in notes:
                    lines.append(f"  - {n['text']}")
                return "\n".join(lines)
            case _:
                return f"Unknown tool '{name}'. Available: " + ", ".join(
                    t["function"]["name"] for t in TOOL_SCHEMAS)

    async def shutdown(self) -> None:
        await self.jobs.shutdown()


def _pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2)
