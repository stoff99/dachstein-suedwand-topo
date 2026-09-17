#!/usr/bin/env python3
"""
Erzeugt web/data/routes.json mit DEMO-Routendaten fuer den Clickdummy.

ACHTUNG: Saemtliche Linienverlaeufe, Schwierigkeitsgrade, Seillaengen, Standplatz-
und Hakenpositionen in dieser Datei sind FREI ERFUNDEN. Die Namen Steinerweg und
Pichlweg bezeichnen zwar echte Routen, die hier hinterlegten Daten haben damit aber
nichts zu tun. Sie dienen ausschliesslich dazu, den Viewer zu testen.

Echte Topodaten entstehen spaeter im Zeichenmodus der Website (web/index.html?edit=1)
und werden von dort als JSON exportiert.

Koordinatensystem: u = 0..1 ueber die Bildbreite, v = 0..1 von oben nach unten.
Normierte Koordinaten deshalb, damit das Topo einen Neu-Export des Panoramas in
anderer Aufloesung unbeschadet uebersteht.

Aufruf:
    python3 tools/make_demo_routes.py
"""

import json
import os

import numpy as np
from scipy.interpolate import PchipInterpolator

ASPECT = 2.0          # Bildbreite : Bildhoehe, fuer laengentreue Rechnung auf der Linie
OUT = "web/data/routes.json"


# --------------------------------------------------------------- Linienwerkzeuge

def resample(points, n=240):
    """Stuetzpunkte zu einer glatten Linie mit n Punkten machen."""
    p = np.asarray(points, dtype=float)
    d = np.diff(p, axis=0) * np.array([ASPECT, 1.0])
    seg = np.hypot(d[:, 0], d[:, 1])
    t = np.concatenate([[0.0], np.cumsum(seg)])
    t /= t[-1]
    fu = PchipInterpolator(t, p[:, 0])
    fv = PchipInterpolator(t, p[:, 1])
    tt = np.linspace(0.0, 1.0, n)
    return np.column_stack([fu(tt), fv(tt)])


def arclen(line):
    d = np.diff(line, axis=0) * np.array([ASPECT, 1.0])
    seg = np.hypot(d[:, 0], d[:, 1])
    return np.concatenate([[0.0], np.cumsum(seg)])


def at(line, s_norm):
    """Punkt bei relativer Bogenlaenge 0..1."""
    s = arclen(line)
    target = np.clip(s_norm, 0.0, 1.0) * s[-1]
    i = int(np.searchsorted(s, target))
    i = max(1, min(i, len(s) - 1))
    f = (target - s[i - 1]) / max(s[i] - s[i - 1], 1e-9)
    return line[i - 1] + (line[i] - line[i - 1]) * f


def offset(line, s_norm, lateral):
    """Punkt bei Bogenlaenge s, seitlich um 'lateral' versetzt (fuer Haken, die
    nicht exakt auf der Ideallinie sitzen)."""
    p0 = at(line, max(0.0, s_norm - 0.004))
    p1 = at(line, min(1.0, s_norm + 0.004))
    d = (p1 - p0) * np.array([ASPECT, 1.0])
    n = np.hypot(*d)
    if n < 1e-9:
        return at(line, s_norm)
    nx, ny = -d[1] / n, d[0] / n          # Normale
    p = at(line, s_norm)
    return np.array([p[0] + nx * lateral / ASPECT, p[1] + ny * lateral])


def r4(x):
    return round(float(x), 4)


# ------------------------------------------------------------------- Routenbau

def build_route(spec, rng):
    line = resample(spec["line"])
    n_p = spec["pitchCount"]

    pitches, protection = [], []
    # Stände in etwa gleichmaessig, mit leichter Streuung wie in echt
    cuts = np.linspace(0.0, 1.0, n_p + 1)
    cuts[1:-1] += rng.uniform(-0.018, 0.018, n_p - 1)
    cuts = np.clip(np.sort(cuts), 0.0, 1.0)

    grades = spec["pitchGrades"]
    notes = spec["pitchNotes"]
    belay_types = spec["belayTypes"]
    total_m = spec["lengthM"]

    for i in range(n_p):
        s0, s1 = cuts[i], cuts[i + 1]
        p = at(line, s1)                      # Stand am oberen Ende der Seillaenge
        length = int(round((s1 - s0) * total_m / 5.0) * 5)
        pitches.append({
            "n": i + 1,
            "grade": grades[i % len(grades)],
            "lengthM": max(15, length),
            "belay": {"u": r4(p[0]), "v": r4(p[1]),
                      "type": belay_types[i % len(belay_types)]},
            "note": notes[i % len(notes)],
        })

        # Zwischensicherungen innerhalb der Seillaenge
        n_pro = rng.integers(spec["proPerPitch"][0], spec["proPerPitch"][1] + 1)
        for k in range(int(n_pro)):
            s = s0 + (s1 - s0) * (k + 1) / (n_pro + 1) + rng.uniform(-0.004, 0.004)
            lat = rng.uniform(-0.010, 0.010)
            q = offset(line, float(np.clip(s, 0.0, 1.0)), lat)
            kind = rng.choice(spec["proTypes"], p=spec["proWeights"])
            protection.append({"type": str(kind), "u": r4(q[0]), "v": r4(q[1]),
                               "pitch": i + 1})

    out = {k: spec[k] for k in (
        "id", "name", "color", "grade", "gradeObl", "lengthM", "firstAscent",
        "character", "protectionRating", "gear", "approach", "descent",
        "aspect", "season", "valleyBase") if k in spec}
    out["pitchCount"] = n_p
    out["line"] = [[r4(a), r4(b)] for a, b in line]
    out["start"] = {"u": r4(line[0][0]), "v": r4(line[0][1])}
    out["top"] = {"u": r4(line[-1][0]), "v": r4(line[-1][1])}
    out["pitches"] = pitches
    out["protection"] = protection
    if "variants" in spec:
        out["variants"] = [{
            "id": v["id"], "name": v["name"], "grade": v["grade"], "note": v["note"],
            "line": [[r4(a), r4(b)] for a, b in resample(v["line"], 90)],
        } for v in spec["variants"]]
    return out


# ------------------------------------------------------------------ Demo-Routen

SPECS = [
    {
        "id": "steinerweg",
        "name": "Steinerweg",
        "color": "#ff5f3d",
        "grade": "VI-",
        "gradeObl": "V+",
        "lengthM": 800,
        "pitchCount": 18,
        "firstAscent": {"who": "PLATZHALTER — Daten nicht recherchiert", "year": None},
        "character": "Lange, logische Pfeilerlinie durch die zentrale Wand. Unten "
                     "plattig, im Mittelteil steile Wandstufen, oben Rissgelände zum Grat.",
        "protectionRating": "Mäßig. Altes Material, mobile Sicherungen zwingend.",
        "gear": "2× 50 m Halbseil, 12 Exen, Keile, Friends 0.3–3, Bandschlingen für Sanduhren",
        "approach": "Von der Hütte über das Schuttfeld zum Wandfuß, ca. 45 min.",
        "descent": "Über den Normalweg — nicht Teil dieses Topos.",
        "aspect": "Süd", "season": "Juli bis September", "valleyBase": "PLATZHALTER",
        "belayTypes": ["2 BH", "BH + NH", "2 NH", "2 BH", "Sanduhr + NH"],
        "pitchGrades": ["IV", "IV+", "V-", "V", "V+", "VI-", "V", "IV+", "V-", "VI-"],
        "pitchNotes": [
            "Plattiger Einstieg, brüchig — Steinschlag beachten",
            "Wasserrille, schöne Kletterei",
            "Verschneidung, Sanduhr am Ausstieg",
            "Quergang nach links, heikel abzusichern",
            "Schlüssellänge: steile Wandstufe",
            "Gehgelände zum Band",
            "Kamin, Klemmkeile legen",
            "Ausgesetzte Kante",
            "Riss, Friends mittlerer Größe",
            "Ausstiegsriss zum Grat",
        ],
        "proTypes": ["piton", "thread", "bolt", "cam"],
        "proWeights": [0.44, 0.22, 0.18, 0.16],
        "proPerPitch": (2, 4),
        # endet am Hohen Dachstein
        "line": [
            [0.5715, 0.798], [0.5762, 0.748], [0.5698, 0.698], [0.5773, 0.645],
            [0.5824, 0.590], [0.5758, 0.535], [0.5820, 0.478], [0.5884, 0.420],
            [0.5818, 0.362], [0.5893, 0.300], [0.5836, 0.235], [0.5890, 0.170],
            [0.5861, 0.118],
        ],
        "variants": [{
            "id": "steinerweg-direkt",
            "name": "Direkte Variante (Demo)",
            "grade": "VI+",
            "note": "Umgeht den Quergang direkt über die Wandstufe. Erfundene Demo-Variante.",
            "line": [[0.5820, 0.478], [0.5945, 0.446], [0.5972, 0.400], [0.5893, 0.300]],
        }],
    },
    {
        "id": "pichlweg",
        "name": "Pichlweg",
        "color": "#38bdf8",
        "grade": "V",
        "gradeObl": "IV+",
        "lengthM": 650,
        "pitchCount": 14,
        "firstAscent": {"who": "PLATZHALTER — Daten nicht recherchiert", "year": None},
        "character": "Klassische Linie über den linken Pfeiler. Durchgehend fester Fels, "
                     "im oberen Drittel genussvolle Wandkletterei.",
        "protectionRating": "Ordentlich für eine Route dieses Alters.",
        "gear": "2× 50 m Halbseil, 10 Exen, Keile, Friends 0.4–2",
        "approach": "Wie Steinerweg, dann nach links zum Wandfuß queren, ca. 55 min.",
        "descent": "Über den Normalweg — nicht Teil dieses Topos.",
        "aspect": "Süd", "season": "Juli bis September", "valleyBase": "PLATZHALTER",
        "belayTypes": ["2 BH", "2 NH", "BH + NH", "Block + NH"],
        "pitchGrades": ["III+", "IV", "IV+", "V-", "IV+", "V", "IV", "V-"],
        "pitchNotes": [
            "Leichter Einstieg über Schrofen",
            "Plattenzone, weit zwischen den Haken",
            "Rissverschneidung",
            "Band nach rechts queren",
            "Steile Wandstufe, gut abgesichert",
            "Schöne Henkelkletterei",
            "Kleiner Überhang links umgehen",
            "Zum Gratabschluss",
        ],
        "proTypes": ["piton", "thread", "bolt", "cam"],
        "proWeights": [0.40, 0.18, 0.24, 0.18],
        "proPerPitch": (2, 4),
        # endet am Torstein
        "line": [
            [0.2382, 0.790], [0.2414, 0.740], [0.2462, 0.690], [0.2428, 0.640],
            [0.2492, 0.585], [0.2534, 0.530], [0.2478, 0.475], [0.2541, 0.420],
            [0.2586, 0.360], [0.2548, 0.300], [0.2604, 0.230], [0.2631, 0.160],
            [0.2631, 0.122],
        ],
    },
    {
        "id": "demo-pfeiler",
        "name": "Demo-Pfeiler",
        "color": "#a3e635",
        "grade": "VI",
        "gradeObl": "V",
        "lengthM": 520,
        "pitchCount": 12,
        "firstAscent": {"who": "Beispielroute, frei erfunden", "year": 2024},
        "character": "Moderne Linie über den markanten Pfeiler. Durchgehend mit "
                     "Bohrhaken saniert, gut für einen ersten großen Wandtag.",
        "protectionRating": "Gut. Bohrhaken, wenige mobile Sicherungen nötig.",
        "gear": "2× 50 m Halbseil, 14 Exen, kleines Keilsortiment",
        "approach": "Vom Wandbuch 20 min nach rechts queren.",
        "descent": "Abseilen über die Route, 6× 50 m.",
        "aspect": "Süd", "season": "Juni bis Oktober", "valleyBase": "Beispielort",
        "belayTypes": ["2 BH", "2 BH", "2 BH", "BH + NH"],
        "pitchGrades": ["IV+", "V", "V+", "VI-", "VI", "V+", "V", "IV+"],
        "pitchNotes": [
            "Pfeilerkante, gut abgesichert",
            "Athletische Wandstelle",
            "Schlüssellänge: kleingriffige Platte",
            "Riss, Friends bis 2",
            "Kante, sehr ausgesetzt",
            "Leichteres Gelände zum Stand",
            "Letzte steile Stufe",
            "Ausstieg auf den Grat",
        ],
        "proTypes": ["bolt", "piton", "cam", "thread"],
        "proWeights": [0.62, 0.14, 0.16, 0.08],
        "proPerPitch": (3, 5),
        # endet an der Mitterspitz
        "line": [
            [0.4182, 0.795], [0.4223, 0.745], [0.4171, 0.695], [0.4238, 0.640],
            [0.4291, 0.585], [0.4232, 0.530], [0.4284, 0.470], [0.4341, 0.410],
            [0.4292, 0.350], [0.4352, 0.285], [0.4308, 0.215], [0.4330, 0.142],
        ],
    },
    {
        "id": "demo-verschneidung",
        "name": "Demo-Verschneidung",
        "color": "#fbbf24",
        "grade": "V+",
        "gradeObl": "V",
        "lengthM": 480,
        "pitchCount": 10,
        "firstAscent": {"who": "Beispielroute, frei erfunden", "year": 1978},
        "character": "Folgt der auffälligen Verschneidung im rechten Wandteil. "
                     "Im Frühsommer oft nass.",
        "protectionRating": "Mäßig, viel selbst absichern.",
        "gear": "2× 50 m Halbseil, 8 Exen, komplettes Keil- und Friendsortiment",
        "approach": "Ganz rechts am Wandfuß, 35 min.",
        "descent": "Über den Grat nach Osten absteigen.",
        "aspect": "Süd", "season": "Juli bis September", "valleyBase": "Beispielort",
        "belayTypes": ["2 NH", "Sanduhr + NH", "BH + NH", "Block"],
        "pitchGrades": ["IV", "IV+", "V", "V+", "V-", "IV+"],
        "pitchNotes": [
            "Einstieg über Schuttband",
            "Verschneidung, feucht",
            "Ausstieg aus der Verschneidung nach rechts",
            "Schlüssellänge: glatter Riss",
            "Wandstufe mit Sanduhren",
            "Gratkletterei zum Ausstieg",
        ],
        "proTypes": ["piton", "cam", "thread", "bolt"],
        "proWeights": [0.36, 0.34, 0.20, 0.10],
        "proPerPitch": (2, 4),
        # endet beim Dirndl
        "line": [
            [0.7184, 0.795], [0.7221, 0.748], [0.7163, 0.700], [0.7212, 0.650],
            [0.7154, 0.595], [0.7192, 0.540], [0.7131, 0.485], [0.7168, 0.430],
            [0.7122, 0.370], [0.7161, 0.310], [0.7108, 0.260], [0.7101, 0.224],
        ],
    },
]


def main():
    rng = np.random.default_rng(7)
    routes = [build_route(s, rng) for s in SPECS]

    doc = {
        "wallId": "dachstein-suedwand",
        "placeholder": True,
        "disclaimer": ("ALLE ROUTENDATEN SIND PLATZHALTER. Linienverläufe, Grade, "
                       "Seillängen, Stand- und Hakenpositionen sind frei erfunden und "
                       "dürfen nicht zur Tourenplanung verwendet werden."),
        "coordinateSystem": "u = 0..1 über die Bildbreite, v = 0..1 von oben nach unten",
        "routes": routes,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write("\n")

    print(f"Geschrieben: {OUT}  ({os.path.getsize(OUT) / 1024:.0f} kB)")
    for r in routes:
        print(f"  {r['name']:22s} {r['grade']:4s} {r['pitchCount']:3d} SL  "
              f"{len(r['protection']):3d} Zwischensicherungen  "
              f"{len(r['line'])} Linienpunkte")


if __name__ == "__main__":
    main()
