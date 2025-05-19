# JARVIS AI

JARVIS AI is a modular, voice-activated personal assistant designed to run across local devices. Inspired by the J.A.R.V.I.S. system from the Marvel Cinematic Universe, this project brings together speech recognition, LLM-based conversation, and text-to-speech — all customizable and locally controlled.

The system is split into three core services: an **agentic AI brain**, a **text-to-speech server**, and a **local LLM inference server** — designed to run on a combination of Raspberry Pi 4 and a PC/Mac server (GPU recommended for XTTS and LLMs).

---

## 🎯 Features

- 🎙️ Voice-activated with wake word **“Jarvis”**
- 🧠 Agentic reasoning (LangChain-based)
- 🔊 Real-time responses using XTTS voice synthesis
- 💻 Runs on local GPU-enabled server (PC/Mac) + Raspberry Pi client
- 📦 Modular design for swapping TTS/LLM/agent components
- 🚧 In-progress support for tools, memory, follow-up intent, and smart home integration

---

## 🖥️ Hardware Requirements

- **Raspberry Pi 4**
  - INMP441 microphone (I²S)
  - PAM8403 amplifier → speakers
- **Server Machine** (Mac or Windows PC)
  - NVIDIA GPU recommended (for XTTS + Ollama)
  - Local network access to Pi

---

## 🧠 Architecture

```
[ Wake Word + Voice Input (Pi) ] --> [ STT (Vosk) ] --> [ LLM / Agent (Ollama / LangChain) ] --> [ TTS (XTTS) ] --> [ .wav audio response → Pi Speaker ]
```

The Raspberry Pi handles:
- Wake word detection (`pvporcupine`)
- Microphone recording (`sounddevice`)
- Transcription (`Vosk`)
- Audio playback

The Mac/PC server handles:
- LLM requests via `Ollama`
- Agentic logic and tool routing via LangChain
- Voice generation via XTTS

---

## 🗂 Folder Breakdown

```bash
jarvis-system/
├── agent_jarvis/         # LangChain agent, memory, and intent routing logic
├── ollama/               # Local LLM server setup using Ollama
├── xtts-server-local/    # XTTS TTS server via Python (GPU-accelerated)
├── xtts-server-docker/   # Dockerized XTTS server (RunPod-compatible)
```

---

## 🚀 Setup Instructions

### 1. Clone the Repo

```bash
git clone https://github.com/yourusername/jarvis-system.git
cd jarvis-system
```

### 2. Install Dependencies (in each subdirectory)

For each service (`xtts`, `agent_jarvis`, etc.), set up a Python virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

> XTTS may require additional build tools (see its folder README).

### 3. Start Ollama Server

```bash
ollama serve --host 0.0.0.0
```

### 4. Start XTTS Server

Local version:
```bash
cd xtts-server-local
python xtts-server.py
```

Or Docker version:
```bash
cd xtts-server-docker
docker build -t xtts .
docker run -p 8000:8000 xtts
```

### 5. Start Agent Jarvis

```bash
cd agent_jarvis
python main.py
```

---

## 📢 Voice Activation (on Raspberry Pi)

The Raspberry Pi continuously listens for the wake word “Jarvis,” then:
1. Records user input
2. Sends it to the server for processing
3. Plays the generated `.wav` response via speaker

Logs and transcriptions are printed in real-time.

---

## 🧪 Current Status

- ✅ Working STT, LLM response, and XTTS playback
- 🔄 Ongoing: agent tools, follow-up intent chaining, memory
- 🔄 In progress: home automation (e.g., lights, 3D printers via API)

---

## 📅 Roadmap

- [ ] Add persistent memory and context tracking
- [ ] Extend toolset (weather, smart home, etc.)
- [ ] Improve fallback handling + freeform response chaining
- [ ] Package as systemd service for Pi
- [ ] Optional web interface for command/response visualization

---

## 📜 License

MIT License (or specify your own)

---

## 🧠 Acknowledgments

- [Ollama](https://ollama.com)
- [TTS by coqui.ai](https://github.com/coqui-ai/TTS)
- [LangChain](https://github.com/langchain-ai/langchain)
- [Porcupine Wake Word](https://github.com/Picovoice/porcupine)