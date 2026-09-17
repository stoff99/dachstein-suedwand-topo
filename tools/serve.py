#!/usr/bin/env python3
"""
Kleiner Entwicklungsserver für web/.

Warum nicht einfach python3 -m http.server: der Browser cacht dort HTML, CSS und JS
über die Heuristik und zeigt nach einer Änderung weiter die alte Datei. Hier werden
Code und Daten mit no-store ausgeliefert, Bildkacheln dagegen ganz normal gecacht -
sonst wird das Zoomen in der Entwicklung unnötig langsam.

    python3 tools/serve.py            # http://localhost:8080
    python3 tools/serve.py --port 9000
"""

import argparse
import functools
import http.server
import os
import socketserver

NO_CACHE_SUFFIXES = (".html", ".css", ".js", ".json", ".map")


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        path = self.path.split("?", 1)[0]
        if path.endswith("/") or path.endswith(NO_CACHE_SUFFIXES):
            self.send_header("Cache-Control", "no-store, max-age=0")
        else:
            # Kacheln dürfen gecacht werden, sonst ruckelt das Zoomen beim Entwickeln.
            # Kurz gehalten als Sicherheitsnetz - die eigentliche Absicherung ist die
            # Version in der Kachel-URL (siehe tools/make_tiles.py).
            self.send_header("Cache-Control", "public, max-age=300")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "404" in (fmt % args):
            super().log_message(fmt, *args)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--dir", default="web")
    args = ap.parse_args()

    root = os.path.abspath(args.dir)
    if not os.path.isdir(root):
        raise SystemExit(f"Ordner nicht gefunden: {root}")

    handler = functools.partial(Handler, directory=root)
    with Server(("127.0.0.1", args.port), handler) as httpd:
        print(f"Topo läuft auf http://localhost:{args.port}   (Ordner: {root})")
        print("Zeichenmodus: http://localhost:%d/?edit=1" % args.port)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
