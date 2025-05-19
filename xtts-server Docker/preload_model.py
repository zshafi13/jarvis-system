import torch
from TTS.api import TTS
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import XttsArgs, XttsAudioConfig
from TTS.config.shared_configs import BaseDatasetConfig

torch.serialization.add_safe_globals([
    XttsConfig,
    XttsArgs,
    BaseDatasetConfig,
    XttsAudioConfig
])

TTS("tts_models/multilingual/multi-dataset/xtts_v2")
