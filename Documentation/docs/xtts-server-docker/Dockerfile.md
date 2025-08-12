# Dockerfile
***
## Overview

This document outlines the setup and configuration of a Docker environment for a Python-based application. The Dockerfile is based on the `python:3.10-slim` image and is designed to prepare an environment for running a text-to-speech (TTS) application.

## Environment Variables

- `COQUI_TOS_AGREED=1`: This environment variable indicates agreement to the terms of service for the Coqui TTS library.
- `TTS_CACHE_PATH=/app/tts_cache`: Specifies the path where TTS cache files are stored.

## System Dependencies

The Dockerfile installs several system dependencies necessary for the application to function:

- `git`
- `ffmpeg`
- `libsndfile1`
- `build-essential`
- `curl`

## Application Setup

1. **Working Directory**: The working directory is set to `/app`.
2. **Python Dependencies**: The application installs Python dependencies listed in `requirements.txt` using `pip`.
3. **Model Preloading**: A script named `preload_model.py` is executed to preload TTS models, and the models are cached in `/app/tts_cache`.
4. **Application Files**: The application copies `handler.py` and an audio file `jarvisclean2.wav` into the Docker image.

## Execution

The Docker container is configured to run `handler.py` using Python when started.


***
###### _Powered by Code Intelligence | DocGen_
