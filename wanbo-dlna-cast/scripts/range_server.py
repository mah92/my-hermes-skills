#!/usr/bin/env python3
"""Tiny HTTP server WITH Range support (reguired by the EShare renderer).
Usage: python3 range_server.py [DIR] [PORT]   # default /tmp/dlna_cast_serve 8000
Do NOT use python3 -m http.server here: no Range => renderer aborts the play.
"""
import os, re, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/dlna_cast_serve"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
os.makedirs(ROOT, exist_ok=True)

class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.client_address[0], fmt % args))

    def do_HEAD(self):
        self._send(False)

    def do_GET(self):
        self._send(True)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Allow", "GET, HEAD, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send(self, with_body):
        path = os.path.normpath(ROOT + self.path)
        if not path.startswith(ROOT) or not os.path.isfile(path):
            self.send_error(404); return
        size = os.path.getsize(path)
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                s, e = m.group(1), m.group(2)
                if s: start = int(s)
                if e: end = int(e)
        length = end - start + 1
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if not with_body:
            return
        with open(path, "rb") as f:
            f.seek(start)
            sent = 0
            while sent < length:
                chunk = f.read(min(65536, length - sent))
                if not chunk: break
                try:
                    self.wfile.write(chunk); self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    sys.stderr.write("  (client aborted after %d bytes)\n" % sent)
                    return
                sent += len(chunk)

print(f"Range-capable server: {ROOT} on 0.0.0.0:{PORT}", file=sys.stderr, flush=True)
ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
