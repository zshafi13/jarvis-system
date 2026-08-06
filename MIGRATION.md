# Migration to a low-latency, Home-Assistant-native Jarvis

This tracks the rebuild described in the architecture plan (Wyoming protocol + Home Assistant
Assist pipeline, replacing the current Flask/LangChain/XTTS stack). See git history / commit
`f4b5649` for the first step (stopped tracking the leaked `agent_jarvis/.env`).

## What's built so far (in this repo, ready to review/adapt)

- **`wyoming-chatterbox-tts/`** — a Wyoming-protocol TTS server wrapping Chatterbox Turbo, using
  `jarvisclean2.wav` for voice cloning, streaming sentence-by-sentence instead of XTTS's blocking
  full-file synthesis. Replaces `xtts-server-local/xtts_server.py`. Protocol handling is modeled on
  the reference `wyoming-piper` implementation; the Chatterbox API call itself should be verified
  against whatever `chatterbox-tts` version you install (see that folder's README).
- **`custom_components/jarvis_agent/`** — a Home Assistant custom integration that's the new
  "brain," replacing `agent_jarvis/agent.py`, `chains/intent_router.py`, and
  `chains/tool_runner.py`. It's a `ConversationEntity` that HA's Assist pipeline can call directly:
  one Ollama tool-calling pass (two if a tool fires) instead of the original's fixed three
  sequential calls, with `get_weather`/`get_stock`/`search_web` ported over unchanged in behavior,
  plus a new `control_home_assistant` tool that delegates device commands to HA's own built-in
  agent. Keeps the JARVIS personality prompt from `agent.py`.

Neither of these has been run yet — they need your actual GPU machine, HA instance, and installed
model weights to test. Treat them as a first draft to validate, not finished code.

## What still needs to happen on your hardware (can't be done from here)

1. **On the GPU Mac/PC** (where Ollama and `xtts_server.py` currently run):
   - Install the official `wyoming-faster-whisper` and `wyoming-piper` and get a *stock* Assist
     pipeline working end-to-end first — this validates the architecture's latency win before any
     custom code is involved.
   - Once that's confirmed fast, set up `wyoming-chatterbox-tts/` from this repo (see its README)
     and swap it in for `wyoming-piper` as the pipeline's TTS engine.
   - Ollama keeps running as-is; `llama3.2` already supports tool calling, so no model change is
     required to start.

2. **On the Raspberry Pi 4** (currently running Porcupine + Vosk):
   - Replace that with `wyoming-satellite` (openWakeWord + mic streaming), pointed at your Home
     Assistant instance. The INMP441 mic / PAM8403 amp wiring doesn't need to change.

3. **In Home Assistant**:
   - Add the Wyoming integration entries for `wyoming-faster-whisper` and (once ready)
     `wyoming-chatterbox-tts`.
   - Copy `custom_components/jarvis_agent/` into your HA config directory's `custom_components/`,
     restart HA, add the "Jarvis Agent" integration via the UI (Ollama host/model, Tavily key,
     default location), and set it as the conversation agent in your Assist pipeline.
   - Expose whatever entities you want Jarvis able to control to the Assist API.

## Verification checklist

- [ ] Stock Assist pipeline (Whisper + Piper default voice) responds noticeably faster than the
      old stack — measure end-of-utterance to first-audio-out.
- [ ] Swapping in `wyoming-chatterbox-tts` keeps that latency win while restoring the cloned voice.
- [ ] "Turn on the kitchen lights" (or similar) is correctly handled via `control_home_assistant`.
- [ ] "What's the weather" / "how's Tesla doing" / general chat still work and still sound like
      Jarvis.
- [ ] The Jarvis Agent conversation entity is usable from the HA conversation panel/API directly,
      not just through the voice satellite — confirms it's still general-purpose, not smart-home-only.

## Still open / not yet remediated

- The leaked Tavily key is untracked going forward but **still present in git history** and still
  live until you rotate it on Tavily's side. Scrubbing history (e.g. `git filter-repo`) plus a
  force-push is a separate, more destructive step — do that deliberately, after rotating the key,
  not as a substitute for rotating it.
