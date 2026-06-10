"""Local speech-to-text via faster-whisper (CTranslate2; runs well on
Apple Silicon). Transcription happens in a thread so the voice loop never
blocks."""

from __future__ import annotations

import asyncio
import logging

import numpy as np

from hearth.config import STTConfig

log = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, cfg: STTConfig):
        from faster_whisper import WhisperModel  # heavy import, defer

        device = "auto" if cfg.device == "auto" else cfg.device
        self.cfg = cfg
        self.model = WhisperModel(cfg.model, device=device,
                                  compute_type="int8")

    async def transcribe(self, pcm16: bytes) -> str:
        """16 kHz mono s16le PCM -> text."""
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        return await asyncio.to_thread(self._run, audio)

    def _run(self, audio: "np.ndarray") -> str:
        segments, _info = self.model.transcribe(
            audio, language=self.cfg.language, vad_filter=False)
        return " ".join(seg.text.strip() for seg in segments).strip()
