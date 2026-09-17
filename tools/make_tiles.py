#!/usr/bin/env python3
"""
Zerschneidet ein grosses Bild in eine Kachel-Pyramide fuer den Topo-Viewer.

Ausgabe im XYZ-Schema (wie Kartenkacheln):  tiles/{z}/{x}/{y}.jpg
Zusaetzlich wird web/data/wall.json mit den technischen Angaben geschrieben, die der
Viewer braucht. Ein bereits vorhandener "meta"-Block in wall.json bleibt erhalten.

DAS IST DAS WERKZEUG FUER SPAETER: sobald das echte Panorama gestitcht ist, genuegt

    python3 tools/make_tiles.py pano.tif

und die Website zeigt das echte Bild. Das Topo muss nicht angepasst werden, weil die
Routen in normierten Koordinaten (0..1) gespeichert sind.

Wer libvips installiert hat, kann stattdessen auch das hier nehmen, es ist schneller:
    vips dzsave pano.tif web/tiles --layout google --suffix .jpg[Q=82]

Aufruf:
    python3 tools/make_tiles.py work/wall_placeholder.jpg
    python3 tools/make_tiles.py pano.tif --out web/tiles --quality 85
    python3 tools/make_tiles.py pano.tif --max-width 2048 --out dist/tiles   # kleine Variante
"""

import argparse
import json
import math
import os
import shutil
import time

from PIL import Image

Image.MAX_IMAGE_PIXELS = None

# Randkacheln werden auf volle Kachelgroesse aufgefuellt, weil Leaflet jede Kachel auf
# tileSize skaliert. Die Fuellfarbe entspricht dem Hintergrund der Website, dadurch ist
# der Uebergang am Bildrand unsichtbar.
DEFAULT_BG = (10, 17, 16)


def build_pyramid(src, out_dir, tile_size=256, quality=82, bg=DEFAULT_BG, verbose=True):
    w, h = src.size
    max_z = max(0, math.ceil(math.log2(max(w, h) / tile_size)))

    if verbose:
        print(f"Quellbild {w} x {h} ({w * h / 1e6:.0f} MPx)")
        print(f"Kachelgroesse {tile_size}, Zoomstufen 0..{max_z}")

    os.makedirs(out_dir, exist_ok=True)
    level = src if src.mode == "RGB" else src.convert("RGB")
    total = 0
    t0 = time.time()

    for z in range(max_z, -1, -1):
        shrink = 2 ** (max_z - z)
        zw = max(1, math.ceil(w / shrink))
        zh = max(1, math.ceil(h / shrink))
        if level.size != (zw, zh):
            level = level.resize((zw, zh), Image.LANCZOS)

        cols = math.ceil(zw / tile_size)
        krows = math.ceil(zh / tile_size)
        zdir = os.path.join(out_dir, str(z))

        for tx in range(cols):
            os.makedirs(os.path.join(zdir, str(tx)), exist_ok=True)
            for ty in range(krows):
                box = (tx * tile_size, ty * tile_size,
                       min((tx + 1) * tile_size, zw), min((ty + 1) * tile_size, zh))
                crop = level.crop(box)
                if crop.size != (tile_size, tile_size):
                    padded = Image.new("RGB", (tile_size, tile_size), bg)
                    padded.paste(crop, (0, 0))
                    crop = padded
                crop.save(os.path.join(zdir, str(tx), f"{ty}.jpg"),
                          "JPEG", quality=quality, optimize=True)
                total += 1

        if verbose:
            print(f"  z={z:2d}  {zw:6d} x {zh:<6d}  {cols:4d} x {krows:<4d} = "
                  f"{cols * krows:6d} Kacheln", flush=True)

    if verbose:
        print(f"{total} Kacheln in {time.time() - t0:.1f}s")
    return {"width": w, "height": h, "tileSize": tile_size, "maxNativeZoom": max_z,
            "tileCount": total}


def dir_size(path):
    return sum(os.path.getsize(os.path.join(r, f))
               for r, _, fs in os.walk(path) for f in fs)


def write_wall_json(path, info, tile_url, source):
    """Technische Angaben schreiben, den redaktionellen meta-Block erhalten.

    Die Kachel-URL bekommt eine Version angehängt. Ohne die zeigen Browser nach einem
    Neuaufbau der Pyramide weiter die alten Kacheln: gleiche Adresse, gleicher Inhalt
    aus dem Cache. Mit Version ändert sich die Adresse und die Kacheln werden neu
    geholt - und dürfen gleichzeitig lange gecacht werden, was sie beim Zoomen schnell
    macht. Genauso beim echten Panorama: ein Neu-Export erreicht damit auch die Leute,
    die die Seite schon einmal offen hatten."""
    data = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            data = {}

    data.setdefault("meta", {
        "name": "Dachstein Südwand",
        "subtitle": "Frontalansicht — PLATZHALTERBILD, kein echtes Foto",
        "placeholder": True,
        "photo": "synthetisch erzeugt mit tools/make_placeholder_wall.py",
        "note": "Sobald das echte Panorama gestitcht ist, mit tools/make_tiles.py ersetzen."
    })
    version = format(int(time.time()), "x")
    data["image"] = {
        "version": version,
        "width": info["width"],
        "height": info["height"],
        "tileSize": info["tileSize"],
        "minZoom": 0,
        "maxNativeZoom": info["maxNativeZoom"],
        "maxZoom": info["maxNativeZoom"] + 3,   # darueber hinaus interpoliert Leaflet
        "tileUrl": f"{tile_url}?v={version}",
        "tileCount": info["tileCount"],
        "source": source,
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return data["image"]["tileUrl"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?", default="work/wall_placeholder.jpg",
                    help="Grossbild, das gekachelt wird")
    ap.add_argument("--out", default="web/tiles", help="Zielordner fuer die Kacheln")
    ap.add_argument("--wall-json", default="web/data/wall.json")
    ap.add_argument("--tile-url", default=None,
                    help="URL-Vorlage fuer den Viewer (Standard: aus --out abgeleitet)")
    ap.add_argument("--tile-size", type=int, default=256)
    ap.add_argument("--quality", type=int, default=82)
    ap.add_argument("--max-width", type=int, default=None,
                    help="Quellbild vorher auf diese Breite verkleinern")
    ap.add_argument("--keep", action="store_true",
                    help="Zielordner nicht vorher leeren")
    args = ap.parse_args()

    if not os.path.exists(args.source):
        raise SystemExit(f"Quellbild nicht gefunden: {args.source}")

    src = Image.open(args.source)
    if args.max_width and src.width > args.max_width:
        nh = round(src.height * args.max_width / src.width)
        print(f"Verkleinere {src.width}x{src.height} -> {args.max_width}x{nh}")
        src = src.convert("RGB").resize((args.max_width, nh), Image.LANCZOS)

    if os.path.isdir(args.out) and not args.keep:
        shutil.rmtree(args.out)

    info = build_pyramid(src, args.out, args.tile_size, args.quality)

    tile_url = args.tile_url or (os.path.basename(args.out.rstrip("/")) + "/{z}/{x}/{y}.jpg")
    final_url = write_wall_json(args.wall_json, info, tile_url,
                                os.path.basename(args.source))

    print(f"Kachelordner: {args.out}  ({dir_size(args.out) / 1e6:.1f} MB)")
    print(f"Geschrieben:  {args.wall_json}  (tileUrl = {final_url})")


if __name__ == "__main__":
    main()
