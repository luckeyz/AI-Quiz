"""Buddy system: persistent store for buddy pairs, shared goals, and notes.

Storage layout under buddy_dir:
  pairs.json  — {user_id: buddy_id} bidirectional map
  goals.json  — {pair_key: [{text, done, created_at}]}
  notes.json  — {recipient_id: [{from_id, text, ts}]}

pair_key is always "smaller_id:larger_id" so each pair has exactly one key.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


def _pair_key(a: str, b: str) -> str:
    return ":".join(sorted([a, b]))


class BuddyStore:
    def __init__(self, buddy_dir: Path):
        self.dir = buddy_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._pairs_path = self.dir / "pairs.json"
        self._goals_path = self.dir / "goals.json"
        self._notes_path = self.dir / "notes.json"

    # -- internal helpers ------------------------------------------------------

    def _read(self, path: Path) -> dict:
        if not path.exists():
            return {}
        return json.loads(path.read_text())

    def _write(self, path: Path, data: dict) -> None:
        path.write_text(json.dumps(data, indent=2))

    # -- pairs -----------------------------------------------------------------

    def pair(self, user_id: str, buddy_id: str) -> str:
        """Register a buddy relationship. Returns a status string."""
        if user_id == buddy_id:
            return "You cannot buddy with yourself."
        pairs = self._read(self._pairs_path)
        existing = pairs.get(user_id)
        if existing == buddy_id:
            return f"You and {buddy_id} are already buddies."
        if existing:
            return (f"You are already paired with {existing}. "
                    "Unpair first with unpair_buddy.")
        if pairs.get(buddy_id) and pairs[buddy_id] != user_id:
            return f"{buddy_id} already has a different buddy."
        pairs[user_id] = buddy_id
        pairs[buddy_id] = user_id
        self._write(self._pairs_path, pairs)
        return f"Paired {user_id} and {buddy_id} as accountability buddies."

    def unpair(self, user_id: str) -> str:
        pairs = self._read(self._pairs_path)
        buddy_id = pairs.pop(user_id, None)
        if buddy_id is None:
            return f"{user_id} has no buddy to unpair from."
        pairs.pop(buddy_id, None)
        self._write(self._pairs_path, pairs)
        return f"Removed buddy pairing between {user_id} and {buddy_id}."

    def buddy_of(self, user_id: str) -> str | None:
        return self._read(self._pairs_path).get(user_id)

    def list_pairs(self) -> list[tuple[str, str]]:
        pairs = self._read(self._pairs_path)
        seen: set[str] = set()
        result: list[tuple[str, str]] = []
        for a, b in pairs.items():
            key = _pair_key(a, b)
            if key not in seen:
                seen.add(key)
                result.append((a, b))
        return result

    # -- goals -----------------------------------------------------------------

    def set_goal(self, user_id: str, goal_text: str) -> str:
        buddy_id = self.buddy_of(user_id)
        if buddy_id is None:
            return f"{user_id} has no buddy. Pair first with pair_buddy."
        key = _pair_key(user_id, buddy_id)
        goals = self._read(self._goals_path)
        pair_goals: list[dict] = goals.get(key, [])
        pair_goals.append({
            "text": goal_text,
            "set_by": user_id,
            "done": False,
            "created_at": time.time(),
        })
        goals[key] = pair_goals
        self._write(self._goals_path, goals)
        return f"Goal set for {user_id} and {buddy_id}: '{goal_text}'."

    def complete_goal(self, user_id: str, goal_index: int) -> str:
        buddy_id = self.buddy_of(user_id)
        if buddy_id is None:
            return f"{user_id} has no buddy."
        key = _pair_key(user_id, buddy_id)
        goals = self._read(self._goals_path)
        pair_goals = goals.get(key, [])
        if not (0 <= goal_index < len(pair_goals)):
            return f"No goal at index {goal_index}. Use buddy_status to list goals."
        pair_goals[goal_index]["done"] = True
        goals[key] = pair_goals
        self._write(self._goals_path, goals)
        text = pair_goals[goal_index]["text"]
        return f"Marked goal {goal_index} as done: '{text}'."

    def get_goals(self, user_id: str) -> list[dict]:
        buddy_id = self.buddy_of(user_id)
        if buddy_id is None:
            return []
        key = _pair_key(user_id, buddy_id)
        return self._read(self._goals_path).get(key, [])

    # -- notes -----------------------------------------------------------------

    def leave_note(self, from_id: str, note_text: str) -> str:
        recipient = self.buddy_of(from_id)
        if recipient is None:
            return f"{from_id} has no buddy to leave a note for."
        notes = self._read(self._notes_path)
        inbox: list[dict] = notes.get(recipient, [])
        inbox.append({"from_id": from_id, "text": note_text, "ts": time.time()})
        notes[recipient] = inbox
        self._write(self._notes_path, notes)
        return f"Note left for {recipient} from {from_id}."

    def pop_notes(self, user_id: str) -> list[dict]:
        """Return and clear all pending notes for user_id."""
        notes = self._read(self._notes_path)
        inbox = notes.pop(user_id, [])
        if inbox:
            self._write(self._notes_path, notes)
        return inbox

    def peek_notes(self, user_id: str) -> list[dict]:
        """Return pending notes without clearing them."""
        return self._read(self._notes_path).get(user_id, [])

    # -- status report ---------------------------------------------------------

    def status_report(self, user_id: str) -> str:
        buddy_id = self.buddy_of(user_id)
        if buddy_id is None:
            return f"{user_id} has no buddy yet."

        lines = [f"Buddy: {buddy_id}"]

        goals = self.get_goals(user_id)
        if goals:
            lines.append("Shared goals:")
            for i, g in enumerate(goals):
                mark = "[x]" if g["done"] else "[ ]"
                lines.append(f"  {i}. {mark} {g['text']} (set by {g['set_by']})")
        else:
            lines.append("No shared goals yet.")

        pending = self.peek_notes(user_id)
        if pending:
            lines.append(f"You have {len(pending)} note(s) from your buddy:")
            for n in pending:
                lines.append(f"  - {n['text']}")
        else:
            lines.append("No pending notes from your buddy.")

        return "\n".join(lines)
