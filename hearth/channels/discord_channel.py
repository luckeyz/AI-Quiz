"""Discord voice channel: full duplex.

Inbound: py-cord voice receive (a streaming Sink) -> downmix 48 kHz stereo
to 16 kHz mono -> VAD turn detection -> Whisper -> agent.
Outbound: agent reply -> TTS PCM -> opus -> the voice channel.

`!join` pulls the bot into your current voice channel; from then on it
listens and answers continuously. `auto_rejoin` reconnects on any drop —
the bot never hangs up. Text messages in guild channels also reach the
agent, so the same brain is usable by typing.
"""

from __future__ import annotations

import asyncio
import io
import logging

import discord
import numpy as np
from discord.ext import commands

from hearth.agent import Agent
from hearth.channels.base import ChannelAdapter
from hearth.config import DiscordConfig, VoiceConfig
from hearth.voice.stt import Transcriber
from hearth.voice.tts import Synthesizer
from hearth.voice.vad import TurnDetector

log = logging.getLogger(__name__)


def downmix_48k_stereo_to_16k_mono(pcm: bytes) -> bytes:
    """Discord gives 48 kHz stereo s16le; VAD/Whisper want 16 kHz mono.
    Average channels, then decimate by 3 (48000/16000)."""
    samples = np.frombuffer(pcm[: len(pcm) // 4 * 4], dtype=np.int16)
    stereo = samples.reshape(-1, 2).astype(np.int32)
    mono = ((stereo[:, 0] + stereo[:, 1]) // 2).astype(np.int16)
    return mono[::3].tobytes()


class StreamingSink(discord.sinks.Sink):
    """py-cord sink that forwards decoded PCM to an asyncio queue per
    speaking user instead of buffering to memory."""

    def __init__(self, loop: asyncio.AbstractEventLoop,
                 queue: "asyncio.Queue[tuple[int, bytes]]"):
        super().__init__()
        self._loop = loop
        self._queue = queue

    def write(self, data: bytes, user: int) -> None:  # called off-loop
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (user, data))

    def cleanup(self) -> None:
        pass


class DiscordChannel(ChannelAdapter):
    name = "discord"

    def __init__(self, agent: Agent, cfg: DiscordConfig,
                 voice_cfg: VoiceConfig):
        super().__init__(agent)
        self.cfg = cfg
        self.voice_cfg = voice_cfg
        self.transcriber = Transcriber(voice_cfg.stt)
        self.synthesizer = Synthesizer(voice_cfg.tts)
        self._voice_client: discord.VoiceClient | None = None
        self._pcm_queue: asyncio.Queue[tuple[int, bytes]] = asyncio.Queue()
        self._detectors: dict[int, TurnDetector] = {}
        self._speak_lock = asyncio.Lock()

    async def run(self) -> None:
        if not self.cfg.bot_token:
            raise RuntimeError("DISCORD_BOT_TOKEN is not set in .env")

        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        bot = commands.Bot(command_prefix=self.cfg.command_prefix,
                           intents=intents)
        channel = self  # closure for command handlers

        @bot.event
        async def on_ready() -> None:
            log.info("Discord connected as %s", bot.user)

        @bot.command(name="join")
        async def join(ctx: commands.Context) -> None:
            if not ctx.author.voice:
                await ctx.send("Join a voice channel first, then `!join`.")
                return
            await channel._join_voice(ctx.author.voice.channel)
            await ctx.send("I'm here. Just talk — I'm always listening.")

        @bot.event
        async def on_voice_state_update(member, before, after) -> None:
            # Never hang up: if we get disconnected, rejoin where we were.
            if (channel.cfg.auto_rejoin and member.id == bot.user.id
                    and before.channel and not after.channel):
                log.warning("Dropped from voice; rejoining %s", before.channel)
                await asyncio.sleep(2)
                await channel._join_voice(before.channel)

        @bot.event
        async def on_message(message: discord.Message) -> None:
            if message.author.bot:
                return
            await bot.process_commands(message)
            if message.content.startswith(channel.cfg.command_prefix):
                return
            reply = await channel.agent.respond(message.content)
            await message.channel.send(reply[:1990])

        self.agent.attach_speaker(self.name, self._speak)
        consumer = asyncio.create_task(self._consume_audio())
        try:
            await bot.start(self.cfg.bot_token)
        finally:
            consumer.cancel()
            self.agent.detach_speaker(self.name)

    # -- inbound audio ---------------------------------------------------------

    async def _join_voice(self, voice_channel: discord.VoiceChannel) -> None:
        if self._voice_client and self._voice_client.is_connected():
            await self._voice_client.move_to(voice_channel)
        else:
            self._voice_client = await voice_channel.connect()
        sink = StreamingSink(asyncio.get_running_loop(), self._pcm_queue)
        self._voice_client.start_recording(sink, self._recording_done)

    async def _recording_done(self, sink: StreamingSink) -> None:
        log.info("Voice recording stream ended")

    async def _consume_audio(self) -> None:
        while True:
            user_id, pcm = await self._pcm_queue.get()
            detector = self._detectors.setdefault(
                user_id, TurnDetector(self.voice_cfg.vad))
            utterance = detector.feed(downmix_48k_stereo_to_16k_mono(pcm))
            if utterance:
                asyncio.create_task(self._handle_utterance(utterance))

    async def _handle_utterance(self, pcm16: bytes) -> None:
        text = await self.transcriber.transcribe(pcm16)
        if not text:
            return
        log.info("Heard: %s", text)
        reply = await self.agent.respond(text)
        await self._speak(reply)

    # -- outbound speech ---------------------------------------------------------

    async def _speak(self, text: str) -> None:
        vc = self._voice_client
        if not vc or not vc.is_connected():
            log.info("(not in voice, skipping speech): %s", text)
            return
        pcm = await self.synthesizer.synthesize(text)
        async with self._speak_lock:
            done = asyncio.Event()
            vc.play(discord.PCMAudio(io.BytesIO(pcm)),
                    after=lambda _e: done.set())
            await done.wait()
