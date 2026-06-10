# Architecture

## One brain, many mouths

There is exactly one `Agent` (hearth/agent.py): one rolling context, one
memory store, one job manager. Channels (Discord, FaceTime) are thin
adapters that convert audio↔text and register a `Speaker` callback for
proactive speech. Talk to it on Discord, switch to FaceTime, and it's the
same conversation — same memory, same running jobs.

## The never-ending conversation

Three mechanisms guarantee the agent "never hangs up":

1. **Rolling context** (`context/rolling.py`) — the live message window has
   a hard token budget. Overflow triggers a *roll*: older turns are
   compressed by the local LLM into a summary block stored in durable
   memory (`~/.hearth/memory/summaries.jsonl`), and the window resets
   around the last N turns. Summaries + pinned facts are re-injected into
   the system prompt on every call, so recall degrades gracefully instead
   of the conversation ever ending. If summarization itself fails, the
   oldest turns are dropped — staying alive beats perfect recall.
2. **Channel supervision** (`channels/base.py`) — `run_forever()` restarts
   crashed adapters with capped exponential backoff; the Discord adapter
   additionally auto-rejoins voice on any disconnect.
3. **launchd** (`hearth install-daemon`) — `KeepAlive=true` resurrects the
   whole daemon at the OS level, and memory is on disk, so even a hard
   crash resumes the same life.

## The turn pipeline

```
audio frames ─► TurnDetector (webrtcvad: 700ms silence = end of turn)
            ─► Transcriber (faster-whisper, in a thread)
            ─► Agent.respond() ─► LLMClient.chat(messages, tools)
                 │                       │
                 │                ┌──────┴───────┐
                 │                │  tool_calls? │
                 │                └──────┬───────┘
                 │          fast tools run inline (email, docs, memory)
                 │          slow tools become Jobs and return a job id
                 ▼
            Synthesizer (say/piper ─► ffmpeg ─► PCM) ─► channel playback
```

A `_turn_lock` serializes turns so concurrent speakers (or a job event
landing mid-turn) can't interleave the context.

## Actions and harnesses

`actions/router.py` defines the tool schemas the LLM sees and dispatches
calls. The two open-ended tools — `agent_task` and `make_website` — go
through `actions/harness.py`, which spawns the configured agent CLI
(default `claude -p "<prompt>" --permission-mode acceptEdits`) in a fresh
workspace under `~/Hearth/workspaces/`. Jobs run as asyncio tasks; the
voice loop never blocks. On completion, `JobManager` fires an event, the
agent composes a natural sentence about it, and speaks it on every live
channel.

Swap in any other agentic harness by changing `actions.harness.claude_cmd`
in config.yaml — anything that takes a prompt and exits is a valid
harness.

## Security posture

- The LLM, STT, and TTS are local; spoken words never leave the machine
  except over the channel transport itself (Discord's servers, or a
  FaceTime call).
- The harness runs with `acceptEdits` confined to per-job workspace dirs
  by working directory. If you give the assistant to other people (a
  public Discord server!), tighten `claude_cmd`'s permission mode — anyone
  who can speak to the bot can spend your compute and invoke tools.
- AppleScript email/call control requires explicit TCC grants
  (Accessibility/Automation); nothing is escalated silently.
