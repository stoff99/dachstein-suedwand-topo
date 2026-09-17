#!/usr/bin/env python3
"""
Liest die Silhouette (Grat gegen Himmel) aus einem Foto und schreibt sie als JSON.

Damit bekommt die Platzhalter-Wand den echten Gratverlauf der Dachstein Südwand,
statt einer erfundenen Zackenlinie. Gespeichert wird nur das Höhenprofil, also eine
Zahlenreihe - kein Bildinhalt.

Erkennung: der Himmel ist deutlich blaustichig (Blau minus Rot über der Schwelle).
Ferne Gebirgszüge im Dunst sind ebenfalls blaustichig und zählen damit als Himmel -
genau richtig, sie gehören nicht zur Silhouette. Gescannt wird von oben, und erst ein
längerer Nichthimmel-Lauf gilt als Fels, sonst lösen dünne Zirren die Kante aus.

Aufruf:
    python3 tools/extract_ridge.py Südwand.jpg --out tools/ridge_dachstein.json
    python3 tools/extract_ridge.py foto.jpg --check work/ridge_check.jpg
"""

import argparse
import json
import os

import numpy as np
from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None


def extract(path, work_width=2000, blue_threshold=20, run=14, smooth=5):
    im = Image.open(path).convert("RGB")
    w0, h0 = im.size
    sw = work_width
    sh = round(h0 * sw / w0)
    a = np.asarray(im.resize((sw, sh), Image.LANCZOS), np.int16)
    r, b = a[:, :, 0], a[:, :, 2]

    sky = (b - r > blue_threshold) & (b > 90)
    cum = np.cumsum((~sky).astype(np.int32), axis=0)

    ridge = np.full(sw, sh - 1, np.float32)
    for x in range(sw):
        col = cum[:, x]
        ok = np.where((col[run:] - col[:-run]) >= run)[0]
        if len(ok):
            ridge[x] = ok[0]

    if smooth:
        pad = np.pad(ridge, smooth, mode="edge")
        ridge = np.convolve(pad, np.ones(2 * smooth + 1) / (2 * smooth + 1), mode="valid")

    return ridge / sh, (sw, sh), (w0, h0), im


def find_peaks(prof, min_gap=0.03, count=12):
    n = len(prof)
    gap = max(3, int(min_gap * n))
    peaks = []
    for x in range(gap // 2, n - gap // 2):
        window = prof[max(0, x - gap):x + gap + 1]
        if prof[x] == window.min() and all(abs(x - p) > gap for p, _ in peaks):
            peaks.append((x, float(prof[x])))
    peaks.sort(key=lambda p: p[1])
    return [{"u": round(x / n, 4), "v": round(v, 4)} for x, v in peaks[:count]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photo")
    ap.add_argument("--out", default="tools/ridge_dachstein.json")
    ap.add_argument("--check", default=None, help="Kontrollbild mit eingezeichneter Linie")
    ap.add_argument("--samples", type=int, default=1200, help="Stützstellen im JSON")
    ap.add_argument("--blue-threshold", type=int, default=20)
    args = ap.parse_args()

    prof, (sw, sh), (w0, h0), im = extract(args.photo, blue_threshold=args.blue_threshold)

    if args.check:
        vis = im.resize((sw, sh), Image.LANCZOS)
        ImageDraw.Draw(vis).line([(x, float(prof[x] * sh)) for x in range(sw)],
                                 fill=(255, 40, 40), width=3)
        os.makedirs(os.path.dirname(args.check) or ".", exist_ok=True)
        vis.save(args.check, quality=90)
        print(f"Kontrollbild: {args.check}")

    xs = np.linspace(0, len(prof) - 1, args.samples)
    sampled = np.interp(xs, np.arange(len(prof)), prof)

    doc = {
        "source": os.path.basename(args.photo),
        "photoSize": [w0, h0],
        "photoAspect": round(w0 / h0, 4),
        "note": ("v ist auf die Fotohöhe normiert, 0 oben. Nur das Höhenprofil des "
                 "Grats, kein Bildinhalt."),
        "vMin": round(float(sampled.min()), 4),
        "vMax": round(float(sampled.max()), 4),
        "peaks": find_peaks(sampled),
        "ridge": [round(float(v), 5) for v in sampled],
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write("\n")

    print(f"Geschrieben: {args.out}  ({args.samples} Stützstellen, "
          f"v={doc['vMin']}..{doc['vMax']}, Fotoformat {doc['photoAspect']}:1)")
    print("Höchste Punkte:")
    for p in doc["peaks"][:6]:
        print(f"  u={p['u']:.3f}  v={p['v']:.3f}")


if __name__ == "__main__":
    main()
