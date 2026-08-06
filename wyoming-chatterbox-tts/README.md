# wyoming-chatterbox-tts

A [Wyoming protocol](https://github.com/rhasspy/wyoming) TTS server that wraps
[Chatterbox Turbo](https://www.resemble.ai/learn/models/chatterbox-turbo) (Resemble AI) instead of
Piper, so the Home Assistant Assist pipeline can speak in the cloned Jarvis/Bettany voice
(`jarvisclean2.wav`) with streaming, low-latency output instead of XTTS's blocking
file-write approach.

This replaces `xtts-server-local/xtts_server.py` in the new architecture. It is deployed on the
same GPU machine that currently runs `xtts_server.py` and Ollama.

## Status

This is a first-pass scaffold, not yet run against a live Chatterbox Turbo install. The Wyoming
protocol handling (`handler.py`) follows the same event flow as the reference
[`wyoming-piper`](https://github.com/rhasspy/wyoming-piper) implementation and should be correct
as-is. The Chatterbox-specific call in `chatterbox_engine.py` is written against the API described
in Resemble AI's docs as of the model's release, but **you should confirm the exact method
signature (`from_pretrained`, `generate`, sample rate, streaming support) against whatever version
of the `chatterbox-tts` package you actually install**, since it's a fast-moving 2026 release and
the API may have shifted. That file is intentionally the only place Chatterbox-specific code
lives, to keep the blast radius of any needed fix small.

## Setup

```bash
cd wyoming-chatterbox-tts
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python3 -m wyoming_chatterbox \
  --uri tcp://0.0.0.0:10201 \
  --speaker-wav ../xtts-server-local/jarvisclean2.wav \
  --device cuda
```

Then in Home Assistant, add a Wyoming integration pointed at
`<this-machine-ip>:10201` and select it as the TTS engine in your Assist pipeline, the same way
you'd add `wyoming-piper`.

## Why sentence-chunked streaming instead of token-level streaming

True token-level streaming TTS (audio for a phrase before the LLM has finished generating the next
one) needs tight coupling between the LLM's token stream and the TTS engine. To keep this service a
drop-in, protocol-correct Wyoming TTS server that HA can talk to like any other, it instead splits
the *incoming* `Synthesize` text on sentence boundaries and streams `AudioChunk` events out
sentence-by-sentence as each one finishes generating, rather than waiting for the entire reply to
synthesize before sending anything. Combined with Chatterbox Turbo's own ~75ms per-call latency,
this is the main latency win over XTTS. If you want true token-level streaming later, that requires
the conversation agent (in `custom_components/jarvis_agent/`) to stream partial LLM output directly
into this service over a side channel instead of going through a single `Synthesize` event — noted
as a possible future iteration, not implemented here.
