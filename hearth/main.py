"""Entrypoint and supervisor.

`hearth run` starts the agent and every enabled channel, each wrapped in
run_forever() so a crashing transport never ends the conversation.
`hearth install-daemon` writes a launchd agent so Hearth starts at login
and is resurrected if it dies — it lives on the machine.
"""

from __future__ import annotations

import asyncio
import logging
import plistlib
import subprocess
import sys
from pathlib import Path

from hearth.agent import Agent
from hearth.config import Config, load_config

log = logging.getLogger(__name__)

LAUNCHD_LABEL = "com.hearth.assistant"


async def run(cfg: Config) -> None:
    agent = Agent(cfg)
    tasks: list[asyncio.Task] = []

    if cfg.channels.discord.enabled:
        from hearth.channels.discord_channel import DiscordChannel
        ch = DiscordChannel(agent, cfg.channels.discord, cfg.voice)
        tasks.append(asyncio.create_task(ch.run_forever(), name="discord"))

    if cfg.channels.facetime.enabled:
        from hearth.channels.facetime_channel import FaceTimeChannel
        ch = FaceTimeChannel(agent, cfg.channels.facetime, cfg.voice)
        tasks.append(asyncio.create_task(ch.run_forever(), name="facetime"))

    if not tasks:
        log.error("No channels enabled in config.yaml — nothing to do.")
        return

    log.info("Hearth is up: %s", ", ".join(t.get_name() for t in tasks))
    try:
        await asyncio.gather(*tasks)
    finally:
        await agent.close()


def install_daemon() -> None:
    python = sys.executable
    cwd = Path.cwd().resolve()
    logs = Path.home() / "Library/Logs/hearth"
    logs.mkdir(parents=True, exist_ok=True)

    plist = {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [python, "-m", "hearth.main", "run"],
        "WorkingDirectory": str(cwd),
        "RunAtLoad": True,
        "KeepAlive": True,  # launchd resurrects the daemon if it dies
        "StandardOutPath": str(logs / "hearth.log"),
        "StandardErrorPath": str(logs / "hearth.err.log"),
    }
    dest = Path.home() / f"Library/LaunchAgents/{LAUNCHD_LABEL}.plist"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(plistlib.dumps(plist))

    subprocess.run(["launchctl", "unload", str(dest)], capture_output=True)
    subprocess.run(["launchctl", "load", str(dest)], check=True)
    print(f"Installed and loaded {dest}")
    print(f"Logs: {logs}/hearth.log")
    print(f"Stop with: launchctl unload {dest}")


def cli() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    command = sys.argv[1] if len(sys.argv) > 1 else "run"
    if command == "run":
        cfg = load_config()
        asyncio.run(run(cfg))
    elif command == "install-daemon":
        install_daemon()
    else:
        print("Usage: hearth [run|install-daemon]")
        sys.exit(2)


if __name__ == "__main__":
    cli()
