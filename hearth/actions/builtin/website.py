"""Website building rides on the agentic harness: we shape the spoken
request into a concrete build prompt and let the agent CLI do the work in
a fresh workspace."""

from __future__ import annotations

WEBSITE_PROMPT = """\
Build a complete static website: {description}

Requirements:
- Plain HTML/CSS/JS in this directory, index.html as the entry point.
- Responsive, clean, modern. No build step required to view it.
- When finished, print a one-paragraph summary of what you built.
"""


def website_prompt(description: str) -> str:
    return WEBSITE_PROMPT.format(description=description)
