# FaceTime channel setup

FaceTime has no public API, so Hearth drives it with macOS automation and
a virtual audio device. One-time setup:

## 1. Install the loopback device

```bash
brew install blackhole-2ch
```

This adds a "BlackHole 2ch" audio device that pipes output to input.

## 2. Point FaceTime at BlackHole

With FaceTime open:

- **Video menu → Microphone → BlackHole 2ch** — what Hearth *plays* into
  BlackHole becomes your voice on the call.
- Route FaceTime's output to BlackHole so Hearth can *hear* the caller.
  FaceTime follows the system output device, so the cleanest setup is a
  **Multi-Output Device** in Audio MIDI Setup (`/Applications/Utilities`)
  containing BlackHole 2ch (+ your speakers if you also want to hear the
  call yourself), set as system output while a call is up.

> Note: with one BlackHole device carrying both directions you can get
> echo (the agent hears itself). For clean duplex, install a second
> loopback (`brew install blackhole-16ch`) and use one device per
> direction — set `input_device` / `output_device` accordingly in
> `config.yaml`.

## 3. Grant permissions

System Settings → Privacy & Security:

- **Accessibility**: allow the process that runs Hearth (Terminal, or the
  launchd context) — needed to click "Accept" on incoming calls.
- **Automation**: allow control of System Events and FaceTime.
- **Microphone**: allow audio capture.

## 4. Enable the channel

```yaml
channels:
  facetime:
    enabled: true
    auto_answer: true
    input_device: "BlackHole 2ch"
    output_device: "BlackHole 2ch"
```

```bash
pip install -e '.[facetime]'
hearth run
```

Now FaceTime the Mac from your phone: the call is auto-answered within a
couple of seconds, the agent greets you, and you're in the same
never-ending conversation (same memory, same jobs) as the Discord channel.

## Caveats

- The "Accept" button automation depends on macOS UI structure and can
  break across macOS releases; `scripts/facetime_answer.applescript`
  checks both the call window and the notification banner. If answering
  stops working after an OS update, that script is the place to fix.
- Apple has no sanctioned way to do this; treat the channel as
  experimental. Discord is the robust path.
