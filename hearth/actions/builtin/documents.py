"""Document writing: drafts land as Markdown in the configured documents
directory. The LLM provides the content; this just persists it safely."""

from __future__ import annotations

import re
import time
from pathlib import Path


def write_document(documents_dir: Path, title: str, content: str) -> str:
    documents_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "note"
    path = documents_dir / f"{time.strftime('%Y-%m-%d')}-{slug}.md"

    counter = 1
    while path.exists():
        path = documents_dir / f"{time.strftime('%Y-%m-%d')}-{slug}-{counter}.md"
        counter += 1

    path.write_text(f"# {title}\n\n{content}\n")
    return f"Saved document to {path}"


def read_document(documents_dir: Path, name_fragment: str) -> str:
    if not documents_dir.exists():
        return "No documents directory yet."
    matches = sorted(documents_dir.glob("*.md"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    matches = [p for p in matches if name_fragment.lower() in p.name.lower()]
    if not matches:
        return f"No document matching '{name_fragment}'."
    text = matches[0].read_text()
    return f"{matches[0].name}:\n{text[:3000]}"
