"""Email checking. Default backend reads Mail.app via AppleScript (no
credentials needed); IMAP is the fallback for machines without Mail.app
configured."""

from __future__ import annotations

import asyncio

from hearth.config import EmailConfig

_APPLESCRIPT = '''
tell application "Mail"
    set unreadMessages to (messages of inbox whose read status is false)
    set output to ""
    set maxCount to {limit}
    set counter to 0
    repeat with msg in unreadMessages
        if counter >= maxCount then exit repeat
        set output to output & "From: " & (sender of msg) & " | Subject: " & (subject of msg) & linefeed
        set counter to counter + 1
    end repeat
    return output
end tell
'''


async def check_email(cfg: EmailConfig) -> str:
    if cfg.backend == "imap":
        return await asyncio.to_thread(_check_imap, cfg)
    return await _check_applescript(cfg)


async def _check_applescript(cfg: EmailConfig) -> str:
    script = _APPLESCRIPT.replace("{limit}", str(cfg.unread_limit))
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        return (f"Couldn't read Mail.app: {err.decode(errors='replace')[:300]}. "
                "Is Mail set up, and does Hearth have Automation permission "
                "in System Settings > Privacy & Security?")
    text = out.decode(errors="replace").strip()
    return text or "Inbox zero — no unread mail."


def _check_imap(cfg: EmailConfig) -> str:
    if not cfg.imap_host:
        return "IMAP backend selected but IMAP_HOST isn't set in .env."
    from imap_tools import MailBox, AND  # optional dependency

    with MailBox(cfg.imap_host).login(cfg.imap_user, cfg.imap_password) as mb:
        lines = [
            f"From: {m.from_} | Subject: {m.subject}"
            for m in mb.fetch(AND(seen=False), limit=cfg.unread_limit,
                              reverse=True, mark_seen=False)
        ]
    return "\n".join(lines) or "Inbox zero — no unread mail."
