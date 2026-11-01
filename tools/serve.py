"""Serve the built site (dist/) as on the hosting: static files with Range requests — the browser seeks in the audio
(python -m http.server can't do them: seeking in the video and the reader wouldn't work).

    make serve   → http://127.0.0.1:8730/
"""
from __future__ import annotations

import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DIST = Path(__file__).resolve().parent.parent / 'dist'


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.m4a': 'audio/mp4', '.webp': 'image/webp',
                      '.mp3': 'audio/mpeg', '.js': 'text/javascript', '.json': 'application/json'}

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(DIST), **kw)

    def log_message(self, fmt, *args):
        pass

    def send_head(self):
        m = re.match(r'bytes=(\d*)-(\d*)$', self.headers.get('Range', ''))
        path = self.translate_path(self.path)
        if not m or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        a = int(m.group(1)) if m.group(1) else max(0, size - int(m.group(2) or 0))
        b = min(int(m.group(2)), size - 1) if m.group(1) and m.group(2) else size - 1
        if a >= size:
            self.send_error(416)
            return None
        f = open(path, 'rb')
        f.seek(a)
        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(path))
        self.send_header('Content-Range', f'bytes {a}-{b}/{size}')
        self.send_header('Content-Length', str(b - a + 1))
        self.send_header('Accept-Ranges', 'bytes')
        self.end_headers()
        self.range_left = b - a + 1
        return f

    def copyfile(self, src, dst):
        left = getattr(self, 'range_left', None)
        if left is None:
            return super().copyfile(src, dst)
        while left > 0:
            chunk = src.read(min(65536, left))
            if not chunk:
                break
            dst.write(chunk)
            left -= len(chunk)

    def end_headers(self):
        if not self.headers.get('Range'):
            self.send_header('Accept-Ranges', 'bytes')
        super().end_headers()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8730
    print(f'site: http://127.0.0.1:{port}/  (Ctrl+C — quit)')
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
