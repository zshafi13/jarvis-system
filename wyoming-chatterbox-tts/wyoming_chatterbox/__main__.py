import argparse
import asyncio
import logging
from functools import partial

from wyoming.info import Attribution, Info, TtsProgram, TtsVoice
from wyoming.server import AsyncServer

from .chatterbox_engine import ChatterboxEngine
from .handler import ChatterboxEventHandler

_LOGGER = logging.getLogger(__name__)


def build_wyoming_info(speaker_wav: str) -> Info:
    return Info(
        tts=[
            TtsProgram(
                name="chatterbox-turbo",
                description="Chatterbox Turbo voice-cloned TTS (Jarvis voice)",
                attribution=Attribution(name="resemble-ai/chatterbox", url="https://www.resemble.ai/"),
                installed=True,
                version="0.1.0",
                voices=[
                    TtsVoice(
                        name="jarvis",
                        description=f"Cloned from {speaker_wav}",
                        attribution=Attribution(name="jarvis-system", url=""),
                        installed=True,
                        version=None,
                        languages=["en"],
                    )
                ],
            )
        ],
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default="tcp://0.0.0.0:10201", help="Wyoming server URI")
    parser.add_argument("--speaker-wav", required=True, help="Reference WAV for voice cloning")
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    engine = ChatterboxEngine(speaker_wav=args.speaker_wav, device=args.device)
    wyoming_info = build_wyoming_info(args.speaker_wav)

    server = AsyncServer.from_uri(args.uri)
    _LOGGER.info("Wyoming Chatterbox TTS server ready on %s", args.uri)
    await server.run(partial(ChatterboxEventHandler, wyoming_info, engine))


if __name__ == "__main__":
    asyncio.run(main())
