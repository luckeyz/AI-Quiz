"""Text-to-speech. Default engine is macOS `say` (zero-install, offline).
Piper is the higher-quality alternative. Both render to 48 kHz stereo s16le
PCM, which is what Discord's opus encoder wants."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from hearth.config import TTSConfig

log = logging.getLogger(__name__)

DISCORD_RATE = 48000


class Synthesizer:
    def __init__(self, cfg: TTSConfig):
        self.cfg = cfg

    async def synthesize(self, text: str) -> bytes:
        """Returns 48 kHz stereo s16le PCM."""
        if self.cfg.engine == "piper":
            return await self._piper(text)
        return await self._say(text)

    async def _say(self, text: str) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as f:
            aiff = Path(f.name)
        try:
            proc = await asyncio.create_subprocess_exec(
                "say", "-v", self.cfg.say_voice,
                "-r", str(self.cfg.say_rate_wpm),
                "-o", str(aiff), text,
            )
            await proc.wait()
            return await self._to_pcm(aiff)
        finally:
            aiff.unlink(missing_ok=True)

    async def _piper(self, text: str) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = Path(f.name)
        try:
            proc = await asyncio.create_subprocess_exec(
                "piper", "--model", str(self.cfg.piper_model.expanduser()),
                "--output_file", str(wav),
                stdin=asyncio.subprocess.PIPE,
            )
            await proc.communicate(text.encode())
            return await self._to_pcm(wav)
        finally:
            wav.unlink(missing_ok=True)

    @staticmethod
    async def _to_pcm(path: Path) -> bytes:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-loglevel", "quiet", "-i", str(path),
            "-f", "s16le", "-ar", str(DISCORD_RATE), "-ac", "2", "pipe:1",
            stdout=asyncio.subprocess.PIPE,
        )
        pcm, _ = await proc.communicate()
        return pcm
