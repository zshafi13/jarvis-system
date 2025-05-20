# File: xtts_server.py
from http.server import BaseHTTPRequestHandler, HTTPServer
from TTS.api import TTS
import json
import torch

# Load model once at startup
tts = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2")
tts.to("cuda" if torch.cuda.is_available() else "cpu")

class TTSHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode())

            text = data.get("text")
            speaker_wav = data.get("speaker_wav", "jarvisclean2.wav")
            language = data.get("language", "en")

            if not text:
                self.send_error(400, "Missing 'text' in request body.")
                return

            print(f"[XTTS] Synthesizing: {text}")
            tts.tts_to_file(
                text=text,
                speaker_wav=speaker_wav,
                language=language,
                file_path="jarvis_reply.wav"
            )

            with open("jarvis_reply.wav", "rb") as f:
                audio_data = f.read()

            # Send back as JSON with base64
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            response = {
                "audio_base64": base64.b64encode(audio_data).decode("utf-8")
            }
            self.wfile.write(json.dumps(response).encode())

        except Exception as e:
            self.send_error(500, f"XTTS server error: {e}")

if __name__ == "__main__":
    print("XTTS server running on http://0.0.0.0:8001")
    HTTPServer(("0.0.0.0", 8001), TTSHandler).serve_forever()
