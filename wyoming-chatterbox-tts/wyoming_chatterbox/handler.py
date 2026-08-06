"""Wyoming event handling, following the same event flow as wyoming-piper."""
from __future__ import annotations

import logging

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.server import AsyncEventHandler
from wyoming.tts import Synthesize

from .chatterbox_engine import ChatterboxEngine

_LOGGER = logging.getLogger(__name__)


class ChatterboxEventHandler(AsyncEventHandler):
    def __init__(self, wyoming_info: Info, engine: ChatterboxEngine, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.wyoming_info = wyoming_info
        self.engine = engine

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info.event())
            return True

        if not Synthesize.is_type(event.type):
            return True

        synthesize = Synthesize.from_event(event)
        text = synthesize.text
        _LOGGER.debug("Synthesizing: %s", text)

        sent_start = False
        for chunk in self.engine.synthesize_sentences(text):
            if not sent_start:
                await self.write_event(
                    AudioStart(rate=chunk.rate, width=chunk.width, channels=chunk.channels).event()
                )
                sent_start = True

            await self.write_event(
                AudioChunk(
                    audio=chunk.audio_int16_bytes,
                    rate=chunk.rate,
                    width=chunk.width,
                    channels=chunk.channels,
                ).event()
            )

        if sent_start:
            await self.write_event(AudioStop().event())
        else:
            _LOGGER.warning("No sentences to synthesize for input: %r", text)

        return True
