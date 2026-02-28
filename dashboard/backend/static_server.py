"""Static server for built dashboard assets with SPA fallback."""

from __future__ import annotations

import argparse
import posixpath
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


class SpaStaticHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, **kwargs):
        self._directory = directory
        super().__init__(*args, directory=directory, **kwargs)

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path).path
        parsed = posixpath.normpath(unquote(parsed))
        parts = [part for part in parsed.split("/") if part]
        resolved = Path(self._directory)
        for part in parts:
            resolved = resolved / part
        return str(resolved)

    def do_GET(self) -> None:
        target = Path(self.translate_path(self.path))
        if target.exists() and target.is_file():
            return super().do_GET()

        index_path = Path(self._directory) / "index.html"
        if index_path.exists():
            self.path = "/index.html"
            return super().do_GET()
        self.send_error(404, "File not found")

    def end_headers(self) -> None:
        # Avoid stale SPA shells after deploys; hashed assets can still be cached safely.
        if self.path.endswith(".html") or self.path == "/":
            self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the built dashboard with SPA fallback.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--dir", default=str(Path(__file__).resolve().parents[1] / "dist"))
    args = parser.parse_args()

    directory = str(Path(args.dir).resolve())
    handler = lambda *a, **kw: SpaStaticHandler(*a, directory=directory, **kw)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving dashboard dist from {directory} on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
