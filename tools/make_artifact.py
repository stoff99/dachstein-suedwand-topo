#!/usr/bin/env python3
"""
Baut aus web/ die veröffentlichbare Variante in dist-artifact/.

Unterschiede zur lokalen Fassung:

* Kleinere Kachel-Pyramide (Standard 4096 px breit statt 12288), damit die Seite mit
  wenigen hundert Dateien auskommt.
* Leaflets Stylesheet wird mitgeliefert statt aus dem CDN geladen. Veröffentlichte
  Seiten dürfen externe Stylesheets nur von Google Fonts holen, Skripte dagegen schon.
* Kein <!doctype>, <html>, <head>, <body>: das Grundgerüst kommt beim Veröffentlichen
  von außen, die Seite liefert nur ihren Inhalt.

Aufruf:
    python3 tools/make_artifact.py [--max-width 4096]
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEAFLET_CSS_URL = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"


def strip_document_shell(html):
    """<!doctype>, <html>, <head>, <body> entfernen - das liefert die Plattform."""
    html = re.sub(r"<!doctype[^>]*>\s*", "", html, flags=re.I)
    html = re.sub(r"</?(html|head|body)\b[^>]*>\s*", "", html, flags=re.I)
    # charset und viewport stellt das Grundgerüst schon bereit
    html = re.sub(r'<meta\s+charset[^>]*>\s*', "", html, flags=re.I)
    html = re.sub(r'<meta\s+name="viewport"[^>]*>\s*', "", html, flags=re.I)
    # Web-App-Angaben entfernen: in einem fremden Rahmen greifen sie nicht, und das
    # Manifest läge dort nicht mit.
    html = re.sub(r'<link rel="manifest"[^>]*>\s*', "", html)
    html = re.sub(r'<meta name="(apple-mobile-web-app|mobile-web-app)[^>]*>\s*', "", html)
    # Leaflet-Stylesheet aus dem CDN gegen die mitgelieferte Datei tauschen
    html = html.replace(
        '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css">',
        '<link rel="stylesheet" href="vendor/leaflet.css">')
    return re.sub(r"\n{3,}", "\n\n", html).strip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-width", type=int, default=4096)
    ap.add_argument("--source", default="work/wall_placeholder.jpg")
    ap.add_argument("--out", default="dist-artifact")
    args = ap.parse_args()

    os.chdir(HERE)
    out = args.out
    vendor_css = os.path.join(out, "vendor", "leaflet.css")
    keep_vendor = os.path.exists(vendor_css)
    vendor_data = open(vendor_css, "rb").read() if keep_vendor else None

    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "vendor"), exist_ok=True)

    if vendor_data:
        open(vendor_css, "wb").write(vendor_data)
    else:
        print(f"Leaflet-Stylesheet fehlt. Einmalig holen:\n"
              f"  mkdir -p {out}/vendor && curl -sS -o {vendor_css} {LEAFLET_CSS_URL}")
        sys.exit(1)

    for name in ("css", "js", "data", "img"):
        shutil.copytree(os.path.join("web", name), os.path.join(out, name))

    with open("web/index.html", encoding="utf-8") as fh:
        page = strip_document_shell(fh.read())
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)

    subprocess.run([sys.executable, "tools/make_tiles.py", args.source,
                    "--max-width", str(args.max_width),
                    "--out", os.path.join(out, "tiles"),
                    "--wall-json", os.path.join(out, "data", "wall.json")], check=True)

    files = [os.path.relpath(os.path.join(r, f), out)
             for r, _, fs in os.walk(out) for f in fs]
    size = sum(os.path.getsize(os.path.join(out, f)) for f in files)
    print(f"\n{out}: {len(files)} Dateien, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
