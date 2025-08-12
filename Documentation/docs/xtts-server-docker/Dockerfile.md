# Dockerfile
***
## Overview

This document outlines the setup and configuration of a Docker container environment for a Python-based application. The container is built using the `python:3.10-slim` image and includes necessary dependencies and configurations for running a text-to-speech (TTS) application.

### Environment Variables

- `COQUI_TOS_AGREED`: Set to `1` to agree to the terms of service for Coqui TTS.
- `TTS_CACHE_PATH`: Specifies the path for caching TTS models.

### System Dependencies

The container installs several system packages:
- `git`
- `ffmpeg`
- `libsndfile1`
- `build-essential`
- `curl`

### Application Setup

- The working directory is set to `/app`.
- Python dependencies are installed from `requirements.txt`.
- A Python script `preload_model.py` is executed to preload TTS models, which are then cached in `/app/tts_cache`.
- The main application script `handler.py` and an audio file `jarvisclean2.wav` are copied into the container.

### Execution

The container runs the application using the command `python handler.py`.


***
###### _Powered by Code Intelligence | DocGen_
