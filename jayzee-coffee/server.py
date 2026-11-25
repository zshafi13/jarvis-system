#!/usr/bin/env python3
"""JayZee Coffee Co - tiny home order server (Python standard library only).

Run:   python3 server.py            (default port 8080)
       python3 server.py --port 9000

Family orders at:   http://<this-computer's-ip>:8080/
Barista screen at:  http://<this-computer's-ip>:8080/barista
"""
import argparse
import json
import socket
import threading
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA = ROOT / "orders.json"
LOCK = threading.Lock()
MAX_TEXT = 200


def load():
    try:
        return json.loads(DATA.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save(orders):
    tmp = DATA.with_suffix(".tmp")
    tmp.write_text(json.dumps(orders, indent=2))
    tmp.replace(DATA)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt, *args):
        pass  # keep the console quiet

    # ---- helpers -------------------------------------------------------
    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 10_000:
            return None
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return None

    def order_id(self):
        parts = self.path.split("?")[0].strip("/").split("/")
        return parts[2] if len(parts) == 3 and parts[:2] == ["api", "orders"] else None

    # ---- routes --------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/orders":
            with LOCK:
                return self.send_json(load())
        if path in ("/barista", "/barista/"):
            self.path = "/barista.html"
        return super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/orders":
            data = self.read_json()
            if not isinstance(data, dict):
                return self.send_json({"error": "bad json"}, 400)
            name = str(data.get("name", "")).strip()[:MAX_TEXT]
            desc = str(data.get("desc", "")).strip()[:MAX_TEXT]
            notes = str(data.get("notes", "")).strip()[:MAX_TEXT]
            if not name or not desc:
                return self.send_json({"error": "name and drink required"}, 400)
            with LOCK:
                orders = load()
                num = (max((o["num"] for o in orders), default=0) % 99) + 1
                order = {
                    "id": uuid.uuid4().hex,
                    "num": num,
                    "name": name,
                    "desc": desc,
                    "notes": notes,
                    "time": int(time.time() * 1000),
                    "done": False,
                }
                orders.append(order)
                save(orders)
            return self.send_json(order, 201)
        if path == "/api/orders/clear-done":
            with LOCK:
                save([o for o in load() if not o["done"]])
            return self.send_json({"ok": True})
        self.send_json({"error": "not found"}, 404)

    def do_PATCH(self):
        oid = self.order_id()
        data = self.read_json()
        if not oid or not isinstance(data, dict):
            return self.send_json({"error": "bad request"}, 400)
        with LOCK:
            orders = load()
            for o in orders:
                if o["id"] == oid:
                    o["done"] = bool(data.get("done"))
                    o["doneTime"] = int(time.time() * 1000) if o["done"] else None
                    save(orders)
                    return self.send_json(o)
        self.send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        oid = self.order_id()
        with LOCK:
            orders = load()
            remaining = [o for o in orders if o["id"] != oid]
            if len(remaining) == len(orders):
                return self.send_json({"error": "not found"}, 404)
            save(remaining)
        self.send_json({"ok": True})


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "localhost"
    finally:
        s.close()


def main():
    ap = argparse.ArgumentParser(description="JayZee Coffee Co order server")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    ip = lan_ip()
    print("JayZee Coffee Co is open!")
    print(f"  Family orders here:  http://{ip}:{args.port}/")
    print(f"  Barista screen:      http://{ip}:{args.port}/barista")
    print("Press Ctrl+C to close up shop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nClosed.")


if __name__ == "__main__":
    main()
