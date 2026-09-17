#!/usr/bin/env python3
"""
Hängt eine Auslieferungskennung an alle eigenen Dateiverweise.

Wozu: GitHub Pages liefert jede Datei mit `Cache-Control: max-age=600` aus, und
eigene Kopfzeilen lassen sich dort nicht setzen. Zehn Minuten lang fragt ein Browser
also gar nicht erst nach, ob es etwas Neues gibt - nach einem Deploy sieht man die
Änderung nicht, oder schlimmer: eine neue Seite mit altem Stylesheet.

Ändert sich dagegen die Adresse, kann nichts aus dem Cache kommen. Genau das macht
dieses Werkzeug: aus `css/app.css` wird `css/app.css?v=a1b2c3d4`. Dieselbe Technik
wie bei den Bildkacheln, siehe make_tiles.py.

Gedacht für den Ablauf in GitHub Actions, der auf einer Wegwerfkopie arbeitet - im
Arbeitsverzeichnis bleiben die Verweise absichtlich sauber, und der lokale
Entwicklungsserver liefert ohnehin ohne Cache aus.

Aufruf:
    python3 tools/stamp_assets.py --build 1a2b3c4d
    python3 tools/stamp_assets.py --build test --dry-run
"""

import argparse
import os
import re
import sys

# Verweise in der Seite: nur eigene, relative Pfade - CDN-Adressen bleiben unberührt.
HTML_REF = re.compile(
    r'((?:href|src)=")((?:css|js|img|data)/[^"?#]+|manifest\.webmanifest)(")')

# Modul-Einbindungen innerhalb der Skripte. Ohne die bliebe topo.js im Cache, auch
# wenn app.js frisch geladen wird.
JS_IMPORT = re.compile(r"((?:from|import\()\s*['\"])(\./[^'\"?#]+\.js)(['\"])")


def stamp(text, build, pattern):
    return pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}?v={build}{m.group(3)}", text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", required=True, help="Kennung, z. B. die Commit-Kurzform")
    ap.add_argument("--dir", default="web")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    build = re.sub(r"[^A-Za-z0-9_.-]", "", args.build)[:32]
    if not build:
        sys.exit("Kennung ist leer")

    changed = 0
    for root, _, files in os.walk(args.dir):
        for name in files:
            if not name.endswith((".html", ".js")):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as fh:
                before = fh.read()
            after = stamp(before, build, HTML_REF if name.endswith(".html") else JS_IMPORT)
            if after == before:
                continue
            changed += 1
            hits = len(re.findall(r"\?v=" + re.escape(build), after))
            print(f"  {path}: {hits} Verweise")
            if not args.dry_run:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(after)

    print(f"{'Gefunden' if args.dry_run else 'Versehen'}: {changed} Dateien, Kennung {build}")


if __name__ == "__main__":
    main()
