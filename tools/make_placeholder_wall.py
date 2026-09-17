#!/usr/bin/env python3
"""
Erzeugt ein synthetisches Bild einer steilen Kalk-Südwand als PLATZHALTER für den
Topo-Clickdummy.

Das Bild ist KEIN Foto der Dachstein Südwand. Es dient nur dazu, Viewer,
Kachel-Pyramide und Topo-Layer zu testen, solange das echte Gigapixel-Panorama noch
nicht gestitcht ist. Spätere Ersetzung:

    python3 tools/make_tiles.py pano.tif

Wie es aufgebaut ist
--------------------
1. **Höhenfeld** — die Wand wird als Tiefenrelief modelliert. Grundlage ist geriffeltes
   fraktales Rauschen mit Domain-Warping (ergibt Pfeiler und Rinnen), in das
   Verschneidungen eingeschnitten und **Schichtbänke** eingeprägt werden. Die
   horizontale Bankung ist das prägende Merkmal von Dachsteinkalk und der Hauptgrund,
   warum reines Rauschen nie nach Kalkwand aussieht.
2. **Schlagschatten** — von jedem Punkt aus wird Richtung Sonne marschiert und geprüft,
   ob etwas davorsteht. Das bringt am meisten Realismus: die harten Schattenkanten
   unter Gesimsen und Überhängen entstehen nur so.
3. **Beleuchtung** — getrennt nach direktem Sonnenlicht (warm, gerichtet, durch den
   Schlagschatten unterbrochen) und Himmelslicht (kühl, diffus, durch
   Umgebungsverdeckung gedämpft). Deshalb sind die Schatten blau und nicht nur dunkel.
4. **Albedo** — Grundgestein, Wasserstreifen, Ockerpatina, Flechten, Schnee auf flachen
   Bändern. Erst das Zusammenspiel aus Albedo und Licht ergibt Tiefe.

Alle Strukturgrößen sind relativ zur Bildgröße. Eine kleine Vorschau (--width 1920)
sieht deshalb genauso aus wie das große Bild, nur weniger detailliert.

Aufruf:
    python3 tools/make_placeholder_wall.py [--width 12288] [--out work/wall_placeholder.jpg]
"""

import argparse
import json
import math
import os
import time

import numpy as np
from PIL import Image
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import map_coordinates

Image.MAX_IMAGE_PIXELS = None

# ----------------------------------------------------------------- Stellschrauben
SUN = np.array([-0.46, -0.60, 0.66], np.float32)     # Richtung zur Sonne (x, y, z)
SUN_COLOR = np.array([1.00, 0.955, 0.875], np.float32) * 1.28
SKY_COLOR = np.array([0.46, 0.585, 0.80], np.float32) * 0.74

ROCK = np.array([194.0, 186.0, 170.0], np.float32)   # trockener, besonnter Kalk
OCHRE = np.array([172.0, 128.0, 78.0], np.float32)   # Patina, Eisenoxid
LICHEN = np.array([126.0, 132.0, 108.0], np.float32)
SNOW = np.array([238.0, 243.0, 250.0], np.float32)

HERE = os.path.dirname(os.path.abspath(__file__))
RIDGE_PROFILE = os.path.join(HERE, "ridge_dachstein.json")
SUMMIT_NAMES = os.path.join(HERE, "summits_dachstein.json")
PROFILE_SPAN = 0.88    # Anteil der Bildbreite, den das Foto abdeckt
RIDGE_TOP = 0.105      # v des höchsten Gipfels im erzeugten Bild

N_BEDS = 30            # Schichtbänke über die Bildhöhe
BED_TILT = 1.15        # Versatz der Bankung über die Bildbreite (Einfallen)
SHADOW_RELIEF = 0.043  # Relieftiefe für den Schlagschatten, Anteil der Bildbreite
SUN_TAN = 0.85         # Tangens der Sonnenhöhe; kleiner = längere Schatten
TARGET_SLOPE = 0.95    # 90. Perzentil der Hangneigung für die Normalenberechnung


# ----------------------------------------------------------------- Rauschbausteine

def _octave(w, h, cx, cy, rng):
    """Value-Noise-Oktave: kleines Zufallsgitter, bikubisch auf w x h aufgezogen.
    cx/cy sind Zellenzahlen, also relativ zur Bildgröße."""
    cx = max(2, min(int(round(cx)), w))
    cy = max(2, min(int(round(cy)), h))
    small = rng.random((cy, cx)).astype(np.float32)
    return np.array(
        Image.fromarray(small, mode="F").resize((w, h), Image.BICUBIC), dtype=np.float32
    )


def fbm(w, h, cx, cy, octaves, rng, persistence=0.5, ridged=False, fx=2.0, fy=2.0):
    """Fraktales Rauschen, Ergebnis etwa 0..1.
    ridged=True erzeugt scharfe Grate statt weicher Hügel.
    fy > fx lässt die anfängliche vertikale Streckung mit jeder Oktave abklingen."""
    acc = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for _ in range(octaves):
        n = _octave(w, h, cx, cy, rng)
        if ridged:
            n = 1.0 - np.abs(2.0 * n - 1.0)
        acc += amp * n
        del n
        total += amp
        amp *= persistence
        cx *= fx
        cy *= fy
    acc *= 1.0 / total
    return acc


def fbm1d(n, cells, octaves, rng, persistence=0.5, ridged=False):
    acc = np.zeros(n, np.float32)
    amp, total, c = 1.0, 0.0, float(cells)
    xs = np.linspace(0.0, 1.0, n)
    for _ in range(octaves):
        m = max(2, int(round(c)))
        small = rng.random(m).astype(np.float32)
        v = np.interp(xs * (m - 1), np.arange(m), small).astype(np.float32)
        if ridged:
            v = 1.0 - np.abs(2.0 * v - 1.0)
        acc += amp * v
        total += amp
        amp *= persistence
        c *= 2.0
    return acc / total


def ridge_from_photo(u, aspect, rng, path=RIDGE_PROFILE, span=PROFILE_SPAN,
                     v_top=RIDGE_TOP):
    """Gratlinie aus dem Silhouettenprofil eines Fotos (tools/extract_ridge.py).

    Formtreu heißt: die senkrechte Überhöhung muss der waagrechten Stauchung folgen.
    Wird das Profil auf span der Bildbreite gestaucht und hat das erzeugte Bild ein
    anderes Seitenverhältnis als das Foto, dann muss v mit
    span * Bildformat / Fotoformat skaliert werden - sonst werden aus den Gipfeln
    flache Hügel.

    Rechts von span endet das Foto. Dort wird der Grat sinngemäß fortgesetzt, damit
    auch der Koppenkarstein noch ins Bild kommt; dieser Teil ist geschätzt."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    prof = np.asarray(doc["ridge"], np.float32)
    scale = span * aspect / float(doc["photoAspect"])
    vmin = float(prof.min())

    w = len(u)
    cut = int(round(span * w))
    src = np.linspace(0.0, len(prof) - 1.0, cut)
    ridge = np.empty(w, np.float32)
    ridge[:cut] = v_top + (np.interp(src, np.arange(len(prof)), prof) - vmin) * scale

    end = float(ridge[cut - 1])
    kx = np.array([span - 0.02, span + 0.030, span + 0.072, 1.0])
    ky = np.array([float(ridge[cut - int(0.02 * w) - 1]),
                   end + 0.052, end - 0.014, end + 0.062])
    ridge[cut:] = PchipInterpolator(kx, ky)(u[cut:]).astype(np.float32)

    # feine Felskanten, damit die Linie beim Hineinzoomen nicht wie gezeichnet wirkt
    ridge += (fbm1d(w, 260, 3, rng) - 0.5) * 0.004

    mapped = []
    for sm in json.load(open(SUMMIT_NAMES, encoding="utf-8"))["summits"]:
        if "photoU" in sm:
            ui = sm["photoU"] * span
        else:
            ui = sm["imageU"]
        xi = int(round(np.clip(ui, 0.0, 1.0) * (w - 1)))
        lo, hi = max(0, xi - w // 220), min(w, xi + w // 220 + 1)
        vi = float(ridge[lo:hi].min())
        mapped.append({"name": sm["name"], "elevation": sm.get("elevation"),
                       "approx": bool(sm.get("approx", False)),
                       "u": round(float(xi) / (w - 1), 4), "v": round(vi, 4)})
    return ridge, mapped


def cells(cx, aspect, stretch=1.0):
    """Zellenzahlen für eine Rauschoktave, unabhängig vom Seitenverhältnis.

    cx zählt die Zellen über die Bildbreite. Die y-Zahl folgt daraus so, dass die
    Zellen quadratisch werden; stretch > 1 streckt die Strukturen senkrecht, wie es
    zu einer Wand passt. Ohne das ändern sich beim Wechsel des Bildformats sämtliche
    Strukturen: aus Pfeilern werden Streifen."""
    return cx, max(2.0, cx / (aspect * stretch))


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def resize_f32(a, w, h, mode=Image.BICUBIC):
    # Image.fromarray(mode="F") interpretiert die Rohbytes als float32. Ein float64-
    # Array ergibt hier stillschweigend Datenmüll, deshalb immer erst konvertieren.
    a = np.ascontiguousarray(a, dtype=np.float32)
    return np.array(Image.fromarray(a, mode="F").resize((w, h), mode), dtype=np.float32)


def blur(a, frac):
    """Weichzeichner mit Radius = frac * Bildbreite, unabhängig von der Bildgröße."""
    h, w = a.shape
    sw = max(2, int(round(1.0 / frac)))
    sh = max(2, int(round(sw * h / w)))
    return resize_f32(resize_f32(a, sw, sh, Image.BILINEAR), w, h)


def normalize(a, lo=2.0, hi=98.0):
    p0, p1 = np.percentile(a[::7, ::7], [lo, hi])
    scale = np.float32(1.0 / max(float(p1 - p0), 1e-6))
    return np.clip((a - np.float32(p0)) * scale, 0.0, 1.0, dtype=np.float32)


def sample_shift(a, sx, sy, fill):
    """out[y, x] = a[y + sy, x + sx], außerhalb mit fill aufgefüllt."""
    h, w = a.shape
    out = np.full((h, w), fill, np.float32)
    ys0, ys1 = max(0, -sy), min(h, h - sy)
    xs0, xs1 = max(0, -sx), min(w, w - sx)
    if ys0 < ys1 and xs0 < xs1:
        out[ys0:ys1, xs0:xs1] = a[ys0 + sy:ys1 + sy, xs0 + sx:xs1 + sx]
    return out


# ------------------------------------------------------------------ Schlagschatten

def cast_shadow(hz, steps, tan_elev, soft):
    """Marschiert von jedem Punkt Richtung Sonne und prüft, ob etwas davorsteht.

    hz ist die Relieftiefe in Pixeln, SUN gibt die Richtung vor. Zurück kommt 0 für
    volle Sonne und 1 für vollständig verschattet."""
    dx, dy = float(SUN[0]), float(SUN[1])
    norm = math.hypot(dx, dy)
    dx, dy = dx / norm, dy / norm
    step_len = 1.0
    best = np.full(hz.shape, -1e9, np.float32)
    for k in range(1, steps + 1):
        sx, sy = int(round(k * dx)), int(round(k * dy))
        shifted = sample_shift(hz, sx, sy, -1e9)
        shifted -= np.float32(k * step_len * tan_elev)
        np.maximum(best, shifted, out=best)
        del shifted
    return smoothstep(0.0, soft, best - hz)


# ----------------------------------------------------------------------- Großform

def macro_height(mw, mh, rng, log, aspect, ridge):
    """Großform: Pfeiler, Rinnen, Verschneidungen und Schichtbänke."""
    log("Großform: geriffeltes Rauschen")
    src = fbm(mw, mh, *cells(9, aspect), 7, rng, persistence=0.54, ridged=True,
              fx=2.0, fy=2.3)

    log("Großform: Domain-Warping")
    wx = fbm(mw, mh, *cells(5, aspect, 0.85), 3, rng, persistence=0.5) - 0.5
    wy = fbm(mw, mh, *cells(5, aspect, 0.85), 3, rng, persistence=0.5) - 0.5
    Y, X = np.mgrid[0:mh, 0:mw].astype(np.float32)
    X += wx * (mw * 0.07)
    Y += wy * (mh * 0.10)
    del wx, wy
    height = map_coordinates(src, [Y, X], order=1, mode="reflect").astype(np.float32)
    del src, X, Y
    height = normalize(height)

    uu = np.linspace(0.0, 1.0, mw, dtype=np.float32)
    vv = np.linspace(0.0, 1.0, mh, dtype=np.float32)

    # -- Rinnen und Verschneidungen einschneiden ----------------------------
    log("Rinnen und Verschneidungen einschneiden")
    n_g = 20
    gaps = rng.uniform(0.45, 1.9, n_g)
    pos = np.cumsum(gaps)
    pos = (pos - pos[0]) / (pos[-1] - pos[0]) * 1.10 - 0.05
    xs = np.arange(mw, dtype=np.float32)[None, :]
    gullies = []

    for i in range(n_g):
        vtop = rng.uniform(0.10, 0.34)
        vbot = rng.uniform(0.70, 0.94)
        if vbot - vtop < 0.28:
            continue
        drift = rng.uniform(-0.05, 0.05)
        centre = (pos[i] + drift * (vv - 0.5)) * mw
        centre += (fbm1d(mh, 5, 6, rng) - 0.5) * mw * 0.022
        halfw = rng.uniform(0.009, 0.032) * mw * (0.45 + 1.1 * vv)
        halfw *= 0.7 + 0.6 * fbm1d(mh, 4, 4, rng)
        strength = rng.uniform(0.26, 0.72)
        depth = (strength
                 * smoothstep(vtop, vtop + 0.12, vv)
                 * smoothstep(vbot, vbot - 0.18, vv))
        d = (xs - centre[:, None]) / halfw[:, None]
        height -= depth[:, None] * np.exp(-np.clip(d * d, 0.0, 30.0)).astype(np.float32)
        del d
        gullies.append((float(centre[-1] / mw), strength))

    # -- Wandstruktur an die Silhouette koppeln -----------------------------
    # Ein Berg ist unter seinem Gipfel nicht hohl: dort steht ein Pfeiler, und unter
    # den Scharten ziehen Rinnen herunter. Ohne diese Kopplung sieht die Silhouette
    # aufgesetzt aus - ein zufälliges Relief mit einer Zackenlinie obendrauf.
    log("Struktur an die Silhouette koppeln")
    r = np.interp(np.linspace(0.0, len(ridge) - 1.0, mw),
                  np.arange(len(ridge)), ridge).astype(np.float32)
    prom = r.max() - r
    prom /= (prom.max() + 1e-9)
    k = max(2, mw // 70)
    prom = np.convolve(np.pad(prom, k, mode="edge"),
                       np.ones(2 * k + 1, np.float32) / (2 * k + 1), mode="valid")
    fade = smoothstep(0.98, 0.12, vv)[:, None]       # oben stark, unten ausklingend
    height += (prom[None, :] - float(prom.mean())) * 0.55 * fade

    height = normalize(height)

    # -- Schichtbänke -------------------------------------------------------
    # Horizontale Bankung mit leichtem Einfallen. Jede Bank bekommt eine eigene
    # Mächtigkeit und einen eigenen Farbton, sonst wirkt es wie ein Streifenmuster.
    log("Schichtbänke")
    warp = fbm(mw, mh, *cells(7, aspect, 0.8), 4, rng, persistence=0.55) - 0.5
    warp += (fbm(mw, mh, *cells(22, aspect, 0.8), 3, rng, persistence=0.5) - 0.5) * 0.55
    phase = (vv[:, None] * N_BEDS + BED_TILT * uu[None, :]).astype(np.float32) + warp * 3.4
    del warp
    idx = np.floor(phase).astype(np.int32)
    saw = (phase - idx).astype(np.float32)
    del phase

    lut_amp = rng.uniform(0.12, 1.0, 97).astype(np.float32) ** 1.6
    lut_tone = rng.uniform(-1.0, 1.0, 97).astype(np.float32)
    sel = np.abs(idx) % 97
    del idx
    amp = lut_amp[sel]
    tone = lut_tone[sel]
    del sel

    # Bankprofil: vorstehendes Gesims am Bankfuß, nach oben zurückweichend.
    # Genau daraus entstehen die hellen Bandkanten mit dem dunklen Saum darunter.
    ledge = np.exp(-np.clip(((saw - 0.12) / 0.14) ** 2, 0.0, 30.0)).astype(np.float32)
    height += amp * (ledge * 0.115 - saw * 0.042)
    del ledge

    return normalize(height), tone, np.array([g[0] for g in gullies], np.float32)


# --------------------------------------------------------------------------- Aufbau

def build(w, h, seed=20250917, verbose=True):
    rng = np.random.default_rng(seed)
    t0 = time.time()

    def log(msg):
        if verbose:
            print(f"  [{time.time() - t0:6.1f}s] {msg}", flush=True)

    u = np.linspace(0.0, 1.0, w, dtype=np.float32)
    rows = np.arange(h, dtype=np.float32)[:, None]
    v_col = rows / h

    # -- Gratlinie aus dem Foto --------------------------------------------
    log("Gratlinie aus Silhouettenprofil")
    ridge, summits = ridge_from_photo(u, w / h, rng)
    ridge = np.clip(ridge, 0.02, 0.62)
    ridge_px = ridge * h

    # -- Wandfuß, Grundverlauf ---------------------------------------------
    # Steht bewusst vor dem Höhenfeld: die Reihenfolge der Zufallszahlen bestimmt,
    # wo Pfeiler und Rinnen liegen, und darauf sind die Demo-Routen gezeichnet.
    # Die Schuttkegel kommen weiter unten dazu, sobald die Rinnen bekannt sind.
    log("Wandfuß")
    base = 0.815 + 0.030 * np.sin(u * 5.3 + 0.8).astype(np.float32)
    base += (fbm1d(w, 11, 5, rng) - 0.5) * 0.070

    # -- Höhenfeld ----------------------------------------------------------
    mw = max(128, w // 3)
    mh = max(48, int(round(mw * h / w)))
    macro, bed_tone_m, gully_pos = macro_height(mw, mh, rng, log, w / h, ridge)

    # Unter jeder Rinne schiebt sich ein Schuttkegel in die Wand hinauf
    for gu in gully_pos:
        wdt = rng.uniform(0.010, 0.026)
        base -= rng.uniform(0.010, 0.032) * np.exp(-((u - gu) / wdt) ** 2)
    base_px = base * h

    log("Schlagschatten")
    zscale = mw * SHADOW_RELIEF
    shadow_m = cast_shadow(macro * zscale, steps=min(240, max(64, mh // 4)),
                           tan_elev=SUN_TAN, soft=zscale * 0.030)

    log("Großform hochskalieren")
    height = resize_f32(macro, w, h)
    shadow = resize_f32(shadow_m, w, h)
    bed_tone = resize_f32(bed_tone_m, w, h)
    del macro, shadow_m, bed_tone_m

    log("Mittlere Struktur")
    mid = fbm(w, h, *cells(40, w / h), 5, rng, persistence=0.52, ridged=True, fx=2.0, fy=2.1)
    height = height * 0.87 + mid * 0.13
    del mid

    # Feinstruktur trägt das Bild beim tiefen Hineinzoomen: ohne sie wirkt der Fels
    # aus der Nähe wie geschmolzenes Plastik.
    log("Feinstruktur")
    fine = fbm(w, h, *cells(260, w / h), 6, rng, persistence=0.58, ridged=True)
    height += (fine - 0.5) * 0.085
    del fine

    # -- Umgebungsverdeckung ------------------------------------------------
    # Zwei Reichweiten: die große erfasst Mulden und Rinnen, die kleine gibt den
    # Blöcken und Kanten aus der Nähe ihre Plastizität.
    log("Umgebungsverdeckung")
    ao = height - blur(height, 1.0 / 22.0)
    ao = smoothstep(-1.8 * np.std(ao), 1.0 * np.std(ao), ao)
    ao_near = height - blur(height, 1.0 / 260.0)
    ao_near = smoothstep(-1.6 * np.std(ao_near), 1.2 * np.std(ao_near), ao_near)
    ao = ao * 0.62 + ao_near * 0.38
    del ao_near
    ao = ao * 0.62 + 0.38

    # -- Normalen und Beleuchtung ------------------------------------------
    # Die Gradienten werden nicht in rohen Pixeleinheiten verwendet: die Feinstruktur
    # hätte dort Neigungen von mehreren hundert Prozent und würde die Großform
    # vollständig überdecken. Stattdessen wird die Neigungsverteilung auf einen
    # Zielwert gebracht - das ist unabhängig von der Bildgröße und steuerbar.
    log("Beleuchtung")
    gy, gx = np.gradient(height)
    p90 = float(np.percentile(np.hypot(gx[::7, ::7], gy[::7, ::7]), 90))
    k = np.float32(TARGET_SLOPE / max(p90, 1e-9))
    gx *= k
    gy *= k
    inv = 1.0 / np.sqrt(gx * gx + gy * gy + 1.0, dtype=np.float32)
    lambert = np.clip((-gx * SUN[0] - gy * SUN[1] + SUN[2]) * inv, 0.0, 1.0)
    facing = inv                      # 1 = frontal, klein = steile Flanke
    del gx, gy

    direct = lambert * (1.0 - shadow)
    del lambert, shadow, height
    ambient = ao * (0.66 + 0.34 * facing)
    del ao

    # -- Albedo -------------------------------------------------------------
    # Die Einzelbeiträge werden zu wenigen Feldern verrechnet, statt jedes einzeln bis
    # zur Komposition mitzuschleppen: bei 50 Megapixeln kostet jedes Feld 200 MB.
    # Gehalten werden am Ende nur alb_mul, tint, snow, bed_tone, rubble, speckle.
    log("Albedo")
    grain = fbm(w, h, *cells(26, w / h), 4, rng, persistence=0.55)

    # dunkle Anteile: Wasserstreifen, Klüfte, Grundkörnung
    wet = smoothstep(0.70, 0.93, fbm(w, h, *cells(220, w / h, 12.0), 5, rng, persistence=0.5, fx=2.0, fy=1.4))
    cracks = smoothstep(0.90, 0.99, fbm(w, h, *cells(190, w / h), 5, rng, persistence=0.55, ridged=True))
    alb_mul = (0.80 + 0.26 * grain) * (1.0 - 0.26 * wet - 0.30 * cracks)
    del wet, cracks
    np.clip(alb_mul, 0.25, 1.15, out=alb_mul)

    # Farbstich: positiv = Ockerpatina, negativ = Flechten
    ochre = smoothstep(0.48, 0.80, fbm(w, h, *cells(16, w / h), 3, rng)) * (0.45 + 0.55 * grain)
    lichen = smoothstep(0.70, 0.90, fbm(w, h, *cells(34, w / h), 3, rng)) * smoothstep(0.55, 0.88, facing)
    tint = ochre * 0.70 - lichen * 0.45
    del ochre, lichen

    log("Schnee auf Bändern")
    snow = (smoothstep(0.93, 0.99, facing)                     # nur wirklich flach
            * smoothstep(0.74, 0.92, fbm(w, h, *cells(30, w / h), 4, rng))
            * smoothstep(0.58, 0.18, v_col))                   # und eher oben
    np.clip(snow, 0.0, 1.0, out=snow)
    del facing, grain

    # -- Komposition, zeilenweise wegen Speicher ---------------------------
    log("Komposition")
    out = np.empty((h, w, 3), np.uint8)
    sky_top = np.array([34.0, 82.0, 156.0], np.float32)
    sky_low = np.array([164.0, 190.0, 214.0], np.float32)
    scree_hi = np.array([136.0, 128.0, 117.0], np.float32)
    scree_lo = np.array([86.0, 86.0, 92.0], np.float32)

    # Blockschutt: feines Korn mit eigener Beleuchtung, damit einzelne Blöcke
    # Schattenseiten bekommen, dazu eine grobe Modulation für Mulden und Rippen.
    # Ohne die gerichtete Komponente wirkt das Schuttfeld wie brauner Nebel.
    gravel = fbm(w, h, *cells(520, w / h), 5, rng, persistence=0.55)
    ggy, ggx = np.gradient(gravel)
    gk = np.float32(0.45 / (np.std(ggx) + 1e-9))
    rubble = np.clip(0.5 - (ggx * 0.55 + ggy * 0.83) * gk, 0.0, 1.0)
    del ggx, ggy, gravel
    rubble = rubble * 0.66 + fbm(w, h, *cells(55, w / h), 3, rng, persistence=0.5) * 0.34
    speckle = fbm(w, h, max(4, w // 6), max(4, h // 6), 3, rng)
    vx = (np.linspace(-1, 1, w, dtype=np.float32) ** 2)[None, :]

    # Schuttkegel: unter jeder Rinne wird das Feld etwas heller
    cone = np.zeros(w, np.float32)
    for gu in gully_pos:
        cone += np.exp(-((u - gu) / 0.035) ** 2)
    cone = np.clip(cone, 0.0, 1.0)

    for y0 in range(0, h, 512):
        y1 = min(h, y0 + 512)
        r = rows[y0:y1]
        sl = slice(y0, y1)

        # Gestein
        alb = ROCK[None, None, :] * alb_mul[sl][:, :, None]
        alb += (bed_tone[sl] * 10.0)[:, :, None]
        t = tint[sl][:, :, None]
        alb = np.where(t > 0,
                       alb * (1.0 - t) + OCHRE * t,
                       alb * (1.0 + t) - LICHEN * t)
        del t
        sn = snow[sl][:, :, None]
        alb = alb * (1.0 - sn) + SNOW * sn

        # Licht: warme Sonne plus kühles Himmelslicht
        light = (direct[sl][:, :, None] * SUN_COLOR
                 + ambient[sl][:, :, None] * SKY_COLOR)
        img = alb * light
        del alb, light, sn

        # weiche Lichterbegrenzung statt hartem Abschneiden
        img = 255.0 * (1.0 - np.exp(-img * (1.04 / 255.0)))

        # Himmel
        sky_t = np.clip(r / (h * 0.55), 0.0, 1.0)[:, :, None]
        sky = sky_top + (sky_low - sky_top) * (sky_t ** 0.9)
        edge = r - ridge_px[None, :]
        is_sky = smoothstep(1.5, -1.5, edge)[:, :, None]
        img = img * (1.0 - is_sky) + sky * is_sky
        rim = np.exp(-np.clip((edge / (h * 0.003)) ** 2, 0.0, 30.0)) * (edge > 0)
        img *= 1.0 - 0.30 * rim[:, :, None]
        del sky, sky_t, is_sky, rim

        # Schuttfeld mit Kegeln
        db = r - base_px[None, :]
        below = smoothstep(-2.0, 4.0, db)[:, :, None]
        depth = np.clip(db / (h * 0.30), 0.0, 1.0)[:, :, None]
        scree = scree_hi + (scree_lo - scree_hi) * depth
        # Blockwerk: grobe Körnung plus feinere Auflösung, damit es beim Hineinzoomen
        # nicht glatt wird, und die Schuttkegel unter den Rinnen etwas heller
        scree *= (0.56 + 0.80 * rubble[sl] + 0.12 * cone[None, :])[:, :, None]
        img = img * (1.0 - below) + scree * below
        del scree, below, depth

        img *= 1.0 - 0.34 * np.exp(-np.clip((db / (h * 0.016)) ** 2, 0.0, 30.0))[:, :, None]
        del db, edge

        haze = (smoothstep(0.80, 1.0, v_col[sl]) * 0.04)[:, :, None]
        img = img * (1.0 - haze) + np.array([176.0, 188.0, 202.0], np.float32) * haze
        img += (speckle[sl][:, :, None] - 0.5) * 13.0
        vy = (np.linspace(-1, 1, h, dtype=np.float32)[sl] ** 2)[:, None]
        img *= (1.0 - 0.15 * np.clip(vx * 0.5 + vy * 0.5, 0.0, 1.0))[:, :, None]

        np.clip(img, 0.0, 255.0, out=img)
        out[sl] = img.astype(np.uint8)
        del img, r, haze

    log("fertig")
    return out, ridge, base, summits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=10240, help="Bildbreite in Pixel")
    ap.add_argument("--aspect", type=float, default=2.0, help="Breite:Höhe")
    ap.add_argument("--summits-out", default="web/data/summits.json",
                    help="Gipfelnamen mit Bildkoordinaten für die Website")
    ap.add_argument("--out", default="work/wall_placeholder.jpg")
    ap.add_argument("--seed", type=int, default=20250917)
    ap.add_argument("--quality", type=int, default=93)
    args = ap.parse_args()

    w = args.width
    h = int(round(w / args.aspect))
    print(f"Erzeuge Platzhalter-Wand {w} x {h} ({w * h / 1e6:.0f} MPx), seed={args.seed}")

    arr, ridge, base, summits = build(w, h, args.seed)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    Image.fromarray(arr, "RGB").save(
        args.out, "JPEG", quality=args.quality, subsampling=0, optimize=True
    )
    print(f"Gespeichert: {args.out}  ({os.path.getsize(args.out) / 1e6:.1f} MB)")
    print(f"Grat v={ridge.min():.3f}..{ridge.max():.3f}, Wandfuß v~{base.mean():.3f}")

    if args.summits_out:
        os.makedirs(os.path.dirname(args.summits_out) or ".", exist_ok=True)
        with open(args.summits_out, "w", encoding="utf-8") as fh:
            json.dump({"note": "Bildkoordinaten der Gipfel, erzeugt von "
                               "tools/make_placeholder_wall.py",
                       "summits": summits}, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        print(f"Gipfel:      {args.summits_out}")
        for sm in summits:
            print(f"  {sm['name']:16s} u={sm['u']:.3f} v={sm['v']:.3f}"
                  + ("  (geschätzt)" if sm["approx"] else ""))


if __name__ == "__main__":
    main()
