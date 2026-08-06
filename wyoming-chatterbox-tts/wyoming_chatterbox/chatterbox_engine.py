"""Thin wrapper around Chatterbox Turbo.

Isolated from the Wyoming protocol handling in handler.py so that if Resemble AI's
API differs from what's assumed here, only this file needs to change.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import torch

_LOGGER = logging.getLogger(__name__)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class SynthesizedChunk:
    audio_int16_bytes: bytes
    rate: int
    width: int = 2
    channels: int = 1


class ChatterboxEngine:
    def __init__(self, speaker_wav: str | Path, device: str = "cuda"):
        from chatterbox.tts import ChatterboxTTS  # imported lazily so --help works without the model

        self.speaker_wav = str(speaker_wav)
        resolved_device = device if (device != "cuda" or torch.cuda.is_available()) else "cpu"
        if resolved_device != device:
            _LOGGER.warning("CUDA not available, falling back to CPU")

        _LOGGER.info("Loading Chatterbox Turbo on %s", resolved_device)
        self.model = ChatterboxTTS.from_pretrained(device=resolved_device)
        self.sample_rate = self.model.sr

    def synthesize_sentences(self, text: str):
        """Yield one SynthesizedChunk per sentence, as each finishes generating.

        Splitting on sentences (rather than synthesizing the whole reply at once)
        is what lets the caller start streaming AudioChunk events to Home Assistant
        before the full reply has finished generating.
        """
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]
        if not sentences:
            return

        for sentence in sentences:
            waveform = self.model.generate(sentence, audio_prompt_path=self.speaker_wav)

            if waveform.dim() == 2:
                waveform = waveform.squeeze(0)

            pcm16 = (waveform.clamp(-1.0, 1.0) * 32767.0).to(torch.int16)
            raw_pcm = pcm16.cpu().numpy().tobytes()

            yield SynthesizedChunk(audio_int16_bytes=raw_pcm, rate=self.sample_rate)
