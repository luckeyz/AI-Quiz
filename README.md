# Hearth — an always-on local voice assistant for macOS

Hearth is a daemon that lives on your Mac, joins real voice conversations
(Discord voice channels today, FaceTime via macOS automation), listens
continuously, talks back with local TTS, and **acts** on what you say by
dispatching work to agentic harnesses (Claude Code, shell jobs, AppleScript).

It never hangs up. The conversation has no end state: context rolls forward
forever through a token-budgeted window that periodically compresses itself
into durable memory, so the agent stays coherent across hours, days, weeks.

```
 ┌─────────────┐   audio    ┌──────────┐  text   ┌─────────────────┐
 │  Discord /  │ ─────────► │ STT (VAD │ ──────► │  Local LLM      │
 │  FaceTime   │ ◄───────── │ +Whisper)│ ◄────── │  (Ollama / LM   │
 └─────────────┘   TTS      └──────────┘         │   Studio, any   │
                                                 │   OpenAI-compat)│
                                                 └───────┬─────────┘
                                                         │ tool calls
                                          ┌──────────────┴──────────────┐
                                          │        Action Router        │
                                          │  claude -p · website · mail │
                                          │  documents · applescript    │
                                          └─────────────────────────────┘
```

## What you can say

- *"Make me a website for my pottery studio"* → spawns a Claude Code harness
  job in a workspace dir, reports back when done, keeps talking meanwhile.
- *"Check my email"* → reads Mail.app via AppleScript (or IMAP), summarizes
  aloud.
- *"Write up a doc about today's plan"* → drafts to `~/Documents/Hearth/`.
- Anything else → conversation. Jobs run in the background; the agent
  narrates progress when you ask or when a job finishes.

## Requirements

- macOS 13+ (Apple Silicon recommended)
- Python 3.11+
- A local LLM server exposing an OpenAI-compatible API:
  - [Ollama](https://ollama.com): `ollama serve` + `ollama pull llama3.1`
  - or LM Studio / llama.cpp server
- `ffmpeg` and `opus` for Discord voice: `brew install ffmpeg opus`
- For Discord: a bot token with the *voice* and *message content* intents
- For agentic actions: `claude` CLI installed (`npm i -g @anthropic-ai/claude-code`)
- For FaceTime audio: [BlackHole](https://existential.audio/blackhole/)
  2ch loopback device (`brew install blackhole-2ch`) — see
  `docs/facetime.md`

## Quick start

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env          # fill in DISCORD_BOT_TOKEN etc.
cp config.example.yaml config.yaml
hearth run                    # foreground
hearth install-daemon         # install launchd agent: survives reboots
```

Then in Discord: invite the bot to your server, join a voice channel, and say
`!join`. The bot enters the channel and the conversation starts — and does
not stop until you kill the daemon.

## Layout

```
hearth/
  main.py               entrypoint + supervisor (auto-restarts channels)
  config.py             config.yaml + .env loading
  llm/client.py         OpenAI-compatible chat client w/ tool calling
  context/rolling.py    infinite rolling context (summarize-and-reset)
  context/memory.py     durable long-term memory store
  voice/stt.py          faster-whisper transcription
  voice/tts.py          macOS `say` / Piper synthesis
  voice/vad.py          webrtcvad turn-taking
  channels/discord_channel.py   full duplex Discord voice
  channels/facetime_channel.py  FaceTime via AppleScript + loopback audio
  actions/router.py     tool schema + dispatch
  actions/harness.py    agentic harness runner (claude -p, shell)
  actions/jobs.py       background job manager
  actions/builtin/      website, email, documents
scripts/                AppleScript helpers
launchd/                com.hearth.assistant.plist template
docs/                   architecture, facetime setup
```

## Design notes

- **Never-ending context** — `context/rolling.py` keeps a hard token budget.
  When the live window exceeds it, the oldest slice is compressed by the LLM
  into a summary block and appended to durable memory; the window "resets"
  around the summary. The conversation is therefore unbounded.
- **Never hangs up** — channel adapters reconnect with backoff; silence
  doesn't end the session; the supervisor restarts crashed adapters.
- **Actions are async** — the voice loop never blocks on a job. Jobs emit
  events that the agent voices on completion.
- **Local-first** — STT, TTS, and the LLM all run on-device by default. The
  only network dependency is the channel transport (Discord) and whatever
  the harness jobs themselves do.
