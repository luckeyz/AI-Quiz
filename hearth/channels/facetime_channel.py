"""FaceTime channel (experimental).

FaceTime has no public API, so this channel is built from two macOS
primitives:

1. **Call control** — AppleScript/System Events auto-answers incoming
   FaceTime calls (scripts/facetime_answer.applescript). Grant the daemon
   Accessibility + Automation permissions in System Settings.
2. **Audio** — a BlackHole loopback device is set as FaceTime's microphone
   and output (FaceTime > Video/Audio menus). We then read the caller's
   voice from BlackHole and write TTS into it via sounddevice/CoreAudio.

See docs/facetime.md for the one-time setup. Once configured, anyone who
FaceTimes this Mac is answered automatically and lands in the same
never-ending conversation as every other channel.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import numpy as np

from hearth.agent import Agent
from hearth.channels.base import ChannelAdapter
from hearth.config import FaceTimeConfig, VoiceConfig
from hearth.voice.stt import Transcriber
from hearth.voice.tts import Synthesizer
from hearth.voice.vad import TurnDetector

log = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
CAPTURE_RATE = 16000
CAPTURE_BLOCK = CAPTURE_RATE // 10  # 100 ms blocks


class FaceTimeChannel(ChannelAdapter):
    name = "facetime"

    def __init__(self, agent: Agent, cfg: FaceTimeConfig,
                 voice_cfg: VoiceConfig):
        super().__init__(agent)
        self.cfg = cfg
        self.voice_cfg = voice_cfg
        self.transcriber = Transcriber(voice_cfg.stt)
        self.synthesizer = Synthesizer(voice_cfg.tts)
        self._speak_lock = asyncio.Lock()
        self._sd = None  # sounddevice, imported lazily

    async def run(self) -> None:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "FaceTime channel needs sounddevice: "
                "pip install 'hearth-assistant[facetime]'") from exc
        self._sd = sd

        self.agent.attach_speaker(self.name, self._speak)
        try:
            tasks = [asyncio.create_task(self._listen_loop())]
            if self.cfg.auto_answer:
                tasks.append(asyncio.create_task(self._answer_loop()))
            await asyncio.gather(*tasks)
        finally:
            self.agent.detach_speaker(self.name)

    # -- auto-answer -------------------------------------------------------------

    async def _answer_loop(self) -> None:
        """Poll for incoming FaceTime calls and accept them."""
        script = SCRIPTS_DIR / "facetime_answer.applescript"
        while True:
            proc = await asyncio.create_subprocess_exec(
                "osascript", str(script),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await proc.communicate()
            if out.strip() == b"answered":
                log.info("Answered an incoming FaceTime call")
                self.agent.context.add_event(
                    "An incoming FaceTime call was just answered. Greet "
                    "the caller.")
                await self._speak("Hey, you've reached the assistant. "
                                  "What can I do for you?")
            elif err and b"not authorized" in err.lower():
                log.error("Missing Accessibility/Automation permission for "
                          "FaceTime control: %s", err.decode()[:200])
            await asyncio.sleep(2)

    # -- audio in ------------------------------------------------------------------

    async def _listen_loop(self) -> None:
        sd = self._sd
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        detector = TurnDetector(self.voice_cfg.vad)

        def callback(indata, _frames, _time, status) -> None:
            if status:
                log.debug("capture status: %s", status)
            mono = indata[:, 0] if indata.ndim > 1 else indata
            pcm = (np.clip(mono, -1, 1) * 32767).astype(np.int16).tobytes()
            loop.call_soon_threadsafe(queue.put_nowait, pcm)

        with sd.InputStream(device=self.cfg.input_device,
                            samplerate=CAPTURE_RATE, channels=1,
                            blocksize=CAPTURE_BLOCK, callback=callback):
            log.info("FaceTime listening on '%s'", self.cfg.input_device)
            while True:
                pcm = await queue.get()
                utterance = detector.feed(pcm)
                if utterance:
                    asyncio.create_task(self._handle_utterance(utterance))

    async def _handle_utterance(self, pcm16: bytes) -> None:
        text = await self.transcriber.transcribe(pcm16)
        if not text:
            return
        log.info("FaceTime heard: %s", text)
        reply = await self.agent.respond(text)
        await self._speak(reply)

    # -- audio out -----------------------------------------------------------------

    async def _speak(self, text: str) -> None:
        sd = self._sd
        pcm48k_stereo = await self.synthesizer.synthesize(text)
        samples = (np.frombuffer(pcm48k_stereo, dtype=np.int16)
                   .reshape(-1, 2).astype(np.float32) / 32768.0)
        async with self._speak_lock:
            await asyncio.to_thread(
                sd.play, samples, 48000, device=self.cfg.output_device,
                blocking=True)
