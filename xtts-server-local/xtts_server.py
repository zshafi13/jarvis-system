# File: xtts_server.py
from http.server import BaseHTTPRequestHandler, HTTPServer
from TTS.api import TTS
import urllib.parse
import torch

tts = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2")
tts.to("cuda" if torch.cuda.is_available() else "cpu")

class TTSHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)
        text = urllib.parse.parse_qs(body.decode())['text'][0]

        self.send_response(200)
        self.send_header('Content-type', 'audio/wav')
        self.end_headers()

        print(f"Generating: {text}")
        tts.tts_to_file(
            text=text,
            speaker_wav="jarvisclean2.wav",  # Use your Bettany sample
            language = "en",
            file_path="jarvis_reply.wav"
        )
        with open("jarvis_reply.wav", "rb") as f:
            self.wfile.write(f.read())

if __name__ == "__main__":
    print("XTTS server running on http://0.0.0.0:8001")
    HTTPServer(("0.0.0.0", 8001), TTSHandler).serve_forever()