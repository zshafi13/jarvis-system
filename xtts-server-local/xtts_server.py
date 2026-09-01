# File: xtts_server.py
from http.server import BaseHTTPRequestHandler, HTTPServer
from TTS.api import TTS
import torch
import json

tts = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2")
tts.to("cuda" if torch.cuda.is_available() else "cpu")

class TTSHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body.decode())
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid JSON")
            return

        text = data.get("text")
        speaker_wav = data.get("speaker_wav", "jarvisclean2.wav")
        language = data.get("language", "en")

        if not text:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'Missing "text" field')
            return

        print(f"Generating: {text}")

        # Generate TTS audio file
        tts.tts_to_file(
            text=text,
            speaker_wav=speaker_wav,
            language=language,
            file_path="jarvis_reply.wav"
        )

        # Send back audio as WAV
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.end_headers()
        with open("jarvis_reply.wav", "rb") as f:
            self.wfile.write(f.read())

if __name__ == "__main__":
    print("XTTS server running on http://0.0.0.0:8001")
    HTTPServer(("0.0.0.0", 8001), TTSHandler).serve_forever()
