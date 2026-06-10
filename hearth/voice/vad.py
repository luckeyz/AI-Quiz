"""Turn-taking: webrtcvad over 16 kHz mono PCM. Feed frames in; get back
completed utterances when the speaker pauses long enough."""

from __future__ import annotations

import webrtcvad

from hearth.config import VADConfig

FRAME_MS = 30
SAMPLE_RATE = 16000
FRAME_BYTES = SAMPLE_RATE * 2 * FRAME_MS // 1000  # 16-bit mono


class TurnDetector:
    def __init__(self, cfg: VADConfig):
        self.cfg = cfg
        self.vad = webrtcvad.Vad(cfg.aggressiveness)
        self._buf = bytearray()
        self._speech = bytearray()
        self._silence_ms = 0
        self._speech_ms = 0

    def feed(self, pcm16: bytes) -> bytes | None:
        """Feed raw 16 kHz mono s16le PCM. Returns a completed utterance's
        PCM when the user's turn ends, else None."""
        self._buf.extend(pcm16)
        utterance: bytes | None = None

        while len(self._buf) >= FRAME_BYTES:
            frame = bytes(self._buf[:FRAME_BYTES])
            del self._buf[:FRAME_BYTES]

            if self.vad.is_speech(frame, SAMPLE_RATE):
                self._speech.extend(frame)
                self._speech_ms += FRAME_MS
                self._silence_ms = 0
            elif self._speech:
                self._speech.extend(frame)  # keep trailing pause for STT
                self._silence_ms += FRAME_MS
                if self._silence_ms >= self.cfg.silence_end_ms:
                    if self._speech_ms >= self.cfg.min_speech_ms:
                        utterance = bytes(self._speech)
                    self._speech.clear()
                    self._speech_ms = 0
                    self._silence_ms = 0

        return utterance
