"""Channel contract. A channel owns a transport (Discord voice, FaceTime
audio), turns inbound audio into text for the agent, and speaks the
agent's replies. Channels must NEVER end the conversation on their own:
run() only returns on cancellation, and transport drops are handled by
reconnecting forever with backoff."""

from __future__ import annotations

import abc
import asyncio
import logging

from hearth.agent import Agent

log = logging.getLogger(__name__)

RECONNECT_BACKOFF_S = (1, 2, 5, 10, 30, 60)


class ChannelAdapter(abc.ABC):
    name: str = "channel"

    def __init__(self, agent: Agent):
        self.agent = agent

    @abc.abstractmethod
    async def run(self) -> None:
        """Connect and serve forever. Raise only on unrecoverable config
        errors; transport failures are reconnected internally."""

    async def run_forever(self) -> None:
        """Supervision wrapper: restart the adapter itself if run() ever
        raises. The conversation does not end."""
        attempt = 0
        while True:
            try:
                await self.run()
                return  # cancelled / clean shutdown
            except asyncio.CancelledError:
                raise
            except Exception:
                delay = RECONNECT_BACKOFF_S[
                    min(attempt, len(RECONNECT_BACKOFF_S) - 1)]
                log.exception("%s channel crashed; restarting in %ss",
                              self.name, delay)
                await asyncio.sleep(delay)
                attempt += 1
