# GPU PC setup (Windows)

This machine runs the three compute-heavy Wyoming services: wake-word detection, STT, and
(later) TTS. Wake word ended up here rather than on the Raspberry Pi 3 because the `pyopen-wakeword`
package's ARM32 wheels are broken upstream (bundle an x86-64 `.so` regardless of the wheel's arch
tag) and neither `tflite-runtime` nor `onnxruntime` currently ship 32-bit ARM wheels at all — not
fixable on our end. Running it here sidesteps that entirely, and streaming raw audio to it over LAN
is cheap (~32kbps, sub-5ms round trip).

Recommended: run everything inside **WSL2 (Ubuntu)** rather than native Windows Python. All three
of these projects (rhasspy/wyoming-*) are built and tested against Linux; WSL2 gets you that
environment plus NVIDIA CUDA passthrough, which now works well in WSL2.

## 1. Install WSL2 + Ubuntu (skip if already set up)

In an **administrator** PowerShell:

```powershell
wsl --install -d Ubuntu
```

Reboot if prompted, then open the "Ubuntu" app from the Start menu and finish the Linux user setup.

## 2. Confirm GPU passthrough works

Inside the Ubuntu/WSL2 shell:

```bash
nvidia-smi
```

You should see your GPU listed. If this fails, install/update the NVIDIA driver on the **Windows**
side (not inside WSL2) from nvidia.com — WSL2 uses the Windows host driver directly.

## 3. Base packages

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git ffmpeg
```

## 4. wyoming-openwakeword (wake word)

```bash
cd ~
git clone https://github.com/rhasspy/wyoming-openwakeword.git
cd wyoming-openwakeword
python3 script/setup   # note: on x86-64 this should install real tflite-runtime/onnxruntime wheels fine
python3 -m wyoming_openwakeword --uri tcp://0.0.0.0:10400 --preload-model hey_jarvis
```

Leave this running (or see step 7 for making it a persistent service). It should print `Ready`.

## 5. wyoming-faster-whisper (STT)

```bash
cd ~
git clone https://github.com/rhasspy/wyoming-faster-whisper.git
cd wyoming-faster-whisper
python3 script/setup
python3 -m wyoming_faster_whisper \
  --uri tcp://0.0.0.0:10300 \
  --model small-int8 \
  --language en \
  --device cuda
```

`small-int8` is a good latency/accuracy starting point on a GPU; bump to `medium-int8` later if
accuracy matters more than raw speed once the pipeline is confirmed fast.

## 6. wyoming-piper (TTS placeholder — gets replaced by wyoming-chatterbox-tts later)

```bash
cd ~
git clone https://github.com/rhasspy/wyoming-piper.git
cd wyoming-piper
python3 script/setup
python3 script/download_voice.py en_US-lessac-medium
python3 -m wyoming_piper \
  --uri tcp://0.0.0.0:10200 \
  --piper ~/wyoming-piper/piper/piper \
  --voice en_US-lessac-medium
```

This is intentionally the *stock* Piper voice, not the cloned Jarvis voice — the point of this step
is to validate the new architecture is actually fast end-to-end before adding the custom TTS. We
add `wyoming-chatterbox-tts` alongside it in the next step.

**Leave Piper running.** Chatterbox goes on its own port (10201), so switching between the cloned
voice and the fast stock one is a single Home Assistant pipeline setting rather than a rebuild.

## 6b. wyoming-chatterbox-tts (the cloned Bettany/JARVIS voice)

```powershell
mkdir C:\Wyoming\wyoming-chatterbox        # copy wyoming_chatterbox/ from this repo into it
copy jarvisclean2.wav C:\Wyoming\          # ~7s reference clip is plenty
cd C:\Wyoming\wyoming-chatterbox
C:\Python311\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install chatterbox-tts "wyoming>=1.5.0"

# MUST come after chatterbox-tts: it depends on plain `torch`, so pip pulls the
# CPU wheel from PyPI and silently overwrites any CUDA build installed earlier.
# Check with: python -c "import torch; print(torch.cuda.is_available())"
.\.venv\Scripts\python.exe -m pip install --force-reinstall `
  torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
```

Then run `run-chatterbox.ps1` from this folder. First start downloads model weights (~4 min);
subsequent starts load in ~10s.

Three things that each fail quietly:

- **Firewall.** The existing "Wyoming Services" rule only covers the ports it was created with.
  Add 10201: `Set-NetFirewallRule -DisplayName "Wyoming Services" -LocalPort 10200,10201,10300,10400 -Protocol TCP`.
  Symptom: the service logs "ready" and listens on 0.0.0.0, but Home Assistant can't reach it.
- **Working directory.** See the comment in `run-chatterbox.ps1`.
- **Language advertisement.** Home Assistant asks for `en_US`, not `en`, and rejects the engine with
  `Language 'en_US' not supported` if only the bare language is advertised.

### Measured performance (RTX 3060, 12GB)

Generation runs at roughly **0.66x realtime** — slower than the audio plays back:

| Reply | Generate | Audio |
|---|---|---|
| "Done." | 1.39s | 0.80s |
| "The garage door is closed." | 1.95s | 1.56s |
| "The P1S Abu is running with about 2 minutes left." | 4.35s | 2.96s |

End-to-end through Home Assistant (which also transcodes to MP3), a device command lands around
4s versus ~0.3s on Piper. That is the price of the cloned voice on this hardware; because
generation is slower than playback, per-sentence streaming improves time-to-first-audio but cannot
close the gap on long replies.

## 7. Windows Firewall / WSL2 networking

This is the part that most commonly silently breaks: WSL2's default NAT networking means ports
opened inside WSL2 aren't automatically reachable from other devices on your LAN (the Pi, Home
Assistant). Two options:

**Option A (simpler, Windows 11 23H2+):** enable WSL2 "mirrored" networking, which makes WSL2 share
the Windows host's network directly. Create/edit `C:\Users\<you>\.wslconfig`:

```ini
[wsl2]
networkingMode=mirrored
```

Then `wsl --shutdown` from PowerShell and reopen Ubuntu.

**Option B:** port-proxy each port from Windows to the WSL2 VM. In an administrator PowerShell
(re-run after every WSL2/Windows restart, since the WSL2 VM's internal IP can change):

```powershell
$wslIp = (wsl hostname -I).Trim().Split()[0]
foreach ($port in 10400,10300,10200) {
    netsh interface portproxy add v4tov4 listenport=$port listenaddress=0.0.0.0 connectport=$port connectaddress=$wslIp
}
New-NetFirewallRule -DisplayName "Wyoming services" -Direction Inbound -Protocol TCP -LocalPort 10200,10300,10400 -Action Allow
```

## Verify from another machine on the LAN

From this Mac, once you've got at least the wake-word service up:

```bash
nc -zv <gpu-pc-ip> 10400
```

Tell me the GPU PC's IP and I'll verify connectivity to all three ports from here once you've got
them running.
