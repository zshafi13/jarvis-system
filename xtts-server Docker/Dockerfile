FROM python:3.10-slim

ENV COQUI_TOS_AGREED=1
ENV TTS_CACHE_PATH=/app/tts_cache

RUN apt-get update && \
    apt-get install -y git ffmpeg libsndfile1 build-essential curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY preload_model.py .
RUN python preload_model.py && \
    mkdir -p /app/tts_cache && \
    cp -r /root/.local/share/tts /app/tts_cache && \
    rm preload_model.py

COPY handler.py .
COPY jarvisclean2.wav .

CMD ["python", "handler.py"]
