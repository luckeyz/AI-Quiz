"""Configuration: config.yaml for behavior, .env for secrets/endpoints."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    model: str = "llama3.1"
    temperature: float = 0.7
    max_tokens: int = 400
    request_timeout_s: float = 120


class ContextConfig(BaseModel):
    window_token_budget: int = 6000
    roll_keep_turns: int = 8
    summary_max_tokens: int = 300
    memory_dir: Path = Path("~/.hearth/memory")


class STTConfig(BaseModel):
    model: str = "small"
    device: str = "auto"
    language: str = "en"


class TTSConfig(BaseModel):
    engine: str = "say"
    say_voice: str = "Samantha"
    say_rate_wpm: int = 190
    piper_model: Path = Path("~/.hearth/voices/en_US-lessac-medium.onnx")


class VADConfig(BaseModel):
    aggressiveness: int = 2
    silence_end_ms: int = 700
    min_speech_ms: int = 250


class VoiceConfig(BaseModel):
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    vad: VADConfig = Field(default_factory=VADConfig)


class DiscordConfig(BaseModel):
    enabled: bool = True
    command_prefix: str = "!"
    auto_rejoin: bool = True
    bot_token: str = ""
    guild_id: str = ""


class FaceTimeConfig(BaseModel):
    enabled: bool = False
    auto_answer: bool = True
    input_device: str = "BlackHole 2ch"
    output_device: str = "BlackHole 2ch"


class ChannelsConfig(BaseModel):
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    facetime: FaceTimeConfig = Field(default_factory=FaceTimeConfig)


class HarnessConfig(BaseModel):
    claude_cmd: list[str] = Field(
        default_factory=lambda: ["claude", "-p", "{prompt}",
                                 "--permission-mode", "acceptEdits"]
    )
    job_timeout_s: int = 3600


class EmailConfig(BaseModel):
    backend: str = "applescript"
    unread_limit: int = 10
    imap_host: str = ""
    imap_user: str = ""
    imap_password: str = ""


class ActionsConfig(BaseModel):
    workspace_dir: Path = Path("~/Hearth/workspaces")
    documents_dir: Path = Path("~/Documents/Hearth")
    harness: HarnessConfig = Field(default_factory=HarnessConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)


class AssistantConfig(BaseModel):
    name: str = "Hearth"
    persona: str = "You are a helpful voice assistant."


class Config(BaseModel):
    assistant: AssistantConfig = Field(default_factory=AssistantConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    actions: ActionsConfig = Field(default_factory=ActionsConfig)


def load_config(path: str | Path = "config.yaml") -> Config:
    load_dotenv()

    raw: dict[str, Any] = {}
    p = Path(path)
    if p.exists():
        raw = yaml.safe_load(p.read_text()) or {}

    cfg = Config.model_validate(raw)

    # Secrets and endpoints come from the environment, never config.yaml.
    cfg.llm.base_url = os.getenv("LLM_BASE_URL", cfg.llm.base_url)
    cfg.llm.api_key = os.getenv("LLM_API_KEY", cfg.llm.api_key)
    cfg.llm.model = os.getenv("LLM_MODEL", cfg.llm.model)
    cfg.channels.discord.bot_token = os.getenv("DISCORD_BOT_TOKEN", "")
    cfg.channels.discord.guild_id = os.getenv("DISCORD_GUILD_ID", "")
    cfg.actions.email.imap_host = os.getenv("IMAP_HOST", "")
    cfg.actions.email.imap_user = os.getenv("IMAP_USER", "")
    cfg.actions.email.imap_password = os.getenv("IMAP_PASSWORD", "")

    for attr_path in ("context.memory_dir", "actions.workspace_dir",
                      "actions.documents_dir"):
        obj = cfg
        *parents, leaf = attr_path.split(".")
        for parent in parents:
            obj = getattr(obj, parent)
        setattr(obj, leaf, getattr(obj, leaf).expanduser())

    return cfg
