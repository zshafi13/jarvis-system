import os
import runpod
from TTS.api import TTS
import torch
import base64
import torch
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import XttsArgs, XttsAudioConfig
from TTS.config.shared_configs import BaseDatasetConfig

torch.serialization.add_safe_globals([
    XttsConfig,
    XttsArgs,
    XttsAudioConfig,
    BaseDatasetConfig
])

SPEAKER_WAV_PATH = "jarvisclean2.wav"

def handler(job):
    """
    RunPod Serverless XTTS handler.
    Expects: job["input"]["text"]
    """
    job_input = job["input"]
    text = job_input.get("text")

    if not text:
        return {"error": "Missing 'text' input."}

    print("Loading XTTS model...")

    os.environ["TTS_CACHE_PATH"] = "/app/tts_cache"
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
    tts.to("cuda" if torch.cuda.is_available() else "cpu")

    output_path = "/tmp/output.wav"
    print(f"Synthesizing: {text}")

    tts.tts_to_file(
        text=text,
        speaker_wav=SPEAKER_WAV_PATH,
        language="en",
        file_path=output_path
    )

    with open(output_path, "rb") as f:
        audio_base64 = base64.b64encode(f.read()).decode("utf-8")

    return {
        "output": {
            "audio_base64": audio_base64,
            "message": f"Synthesized: {text}"
        }
    }

runpod.serverless.start({"handler": handler})
