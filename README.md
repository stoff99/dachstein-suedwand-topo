# Online-Topo Dachstein Südwand — Clickdummy

Klickbarer Prototyp für eine zoombare Online-Topo im alpinen Bergsteigen: ein
hochauflösendes Frontalbild der Wand, darüber ein Topo-Layer mit Routenlinien,
Standplätzen und Haken. Klick auf eine Route blendet die anderen aus und zeigt die
Details mit Seillängen, Graden und Absicherung.

> **Alles in diesem Prototyp ist Platzhalter.** Das Wandbild ist synthetisch erzeugt
> und zeigt nicht die echte Dachstein Südwand. Sämtliche Routenlinien, Grade,
> Seillängen sowie Stand- und Hakenpositionen sind frei erfunden. Die Namen
> *Steinerweg* und *Pichlweg* bezeichnen echte Routen, die hinterlegten Daten haben
> damit aber nichts zu tun. **Nicht zur Tourenplanung geeignet.**

## Starten

```bash
python3 tools/serve.py
```

Dann <http://localhost:8080> öffnen. Zeichenmodus: <http://localhost:8080/?edit=1>

Über `file://` funktioniert es nicht, weil die Daten per `fetch` geladen werden.

Falls die Kacheln fehlen (frischer Klon), einmal neu erzeugen:

```bash
python3 tools/make_placeholder_wall.py
python3 tools/make_tiles.py work/wall_placeholder.jpg
python3 tools/make_demo_routes.py
```

Der Wandgenerator braucht in voller Größe rund 4 GB Arbeitsspeicher und etwa eine
halbe Minute. Für einen schnellen Blick genügt `--width 1920`: alle Strukturgrößen
sind relativ zur Bildgröße, die kleine Vorschau sieht deshalb genauso aus, nur
weniger detailliert.

## Veröffentlichen auf GitHub Pages

Für den Prototyp reicht GitHub Pages: 17 MB, größte Datei 68 kB — weit unter den
Grenzen von 1 GB je Repository und 100 MB je Datei. Eigene Adresse, kein fremder
Rahmen drumherum, und die Web-App-Einstellungen greifen dort (siehe unten).

1. Leeres Repository auf GitHub anlegen, dann:

   ```bash
   git remote add origin git@github.com:BENUTZER/REPO.git
   git push -u origin main
   ```

2. Im Repository unter **Settings → Pages** als Quelle **GitHub Actions** wählen.

3. Fertig. `.github/workflows/pages.yml` veröffentlicht den Ordner `web/` bei jedem
   Push auf `main`. Die Seite liegt danach unter
   `https://BENUTZER.github.io/REPO/`.

Alle Pfade in der Seite sind relativ, sie funktioniert deshalb auch in einem
Unterverzeichnis. Die Bildkacheln liegen fertig im Repository und werden nicht in der
Cloud erzeugt — das entspricht dem späteren Ablauf: Stitchen und Kacheln passiert
lokal, hochgeladen wird das Ergebnis.

**Als App auf dem Handy:** Seite in Safari oder Chrome öffnen, Teilen → *Zum
Home-Bildschirm*. Dann startet sie bildschirmfüllend ohne Browserleiste, mit dem Logo
als Symbol. Dafür sorgen `web/manifest.webmanifest` und die Symbole in `web/img/`.

**Nicht für das echte Panorama.** Zwei Gigapixel ergeben 2–4 GB Kacheln — das sprengt
GitHub Pages (1 GB Richtwert je Repository, 100 GB Datenvolumen im Monat). Dann auf
Cloudflare R2 (kein Entgelt für ausgehenden Verkehr) oder Netlify wechseln; an der
Seite selbst ändert sich dabei nichts, nur `tileUrl` in `web/data/wall.json`.

## Wie das Bild funktioniert

Die rund 250 Teleaufnahmen werden **nicht** einzeln im Browser nebeneinandergelegt.
Stattdessen:

1. **Aufnehmen** — Stativ mit Nodalpunktadapter, Tele 200–400 mm, durchgehend manuell
   (Belichtung, Fokus, Weißabgleich), RAW, etwa 30 % Überlappung, reihenweises Raster
   von **einem einzigen Standpunkt**. Gleichmäßiges Licht: bedeckt oder durchgehend
   Sonne, kein Wolkenschatten, der während der Serie durch die Wand wandert.
   200–300 Bilder ergeben 1–3 Gigapixel.

2. **Stitchen** — alle Aufnahmen werden *einmal offline* zu einem einzigen Panorama
   zusammengesetzt. [PTGui Pro](https://ptgui.com) ist dafür die bewährte Wahl,
   [Hugin](https://hugin.sourceforge.io) die kostenlose Alternative. Export als flaches
   TIFF oder PSB.

   Das ist der entscheidende Schritt: erst das durchgehende Panorama liefert ein
   einheitliches Koordinatensystem. Ohne das springen Routenlinien an Fotogrenzen, und
   Belichtungsunterschiede zwischen Einzelbildern werden als Kanten sichtbar.

3. **Kacheln** — das Panorama wird in 256-Pixel-Kacheln über mehrere Zoomstufen
   zerschnitten (`tiles/{z}/{x}/{y}.jpg`). Der Viewer lädt immer nur die zwanzig bis
   dreißig Kacheln, die gerade im Bild sind.

   ```bash
   python3 tools/make_tiles.py pano.tif           # funktioniert immer
   vips dzsave pano.tif web/tiles --layout google --suffix .jpg[Q=82]   # schneller
   ```

4. **Ausliefern** — die Kacheln sind statische Dateien, es braucht keinen
   Anwendungsserver. Größenordnung: 2 Gigapixel ≈ 40.000 Kacheln ≈ 2–4 GB.
   Cloudflare R2 ist hier sinnvoll, weil es keine Egress-Kosten hat; Netlify geht
   ebenfalls. GitHub Pages ist mit 1 GB zu knapp.

Beim Wechsel auf das echte Panorama muss am Topo nichts angepasst werden — die Routen
liegen in normierten Koordinaten (siehe unten). Nur neu gezeichnet werden müssen sie,
weil ein anderes Foto eine andere Perspektive hat.

**Kachel-Version.** `make_tiles.py` hängt an die Kachel-URL eine Version an
(`tiles/{z}/{x}/{y}.jpg?v=6aabab65`) und schreibt sie in `wall.json`. Ohne die zeigen
Browser nach einem Neuaufbau der Pyramide weiter die alten Kacheln — gleiche Adresse,
gleicher Inhalt aus dem Cache. Mit Version ändert sich die Adresse bei jedem Neuaufbau,
die Kacheln werden neu geholt und dürfen gleichzeitig lange gecacht werden, was das
Zoomen schnell macht. Das gilt genauso für den Echtbetrieb: ein Neu-Export des
Panoramas erreicht so auch die Leute, die die Seite schon einmal offen hatten.

## Topo-Daten

`web/data/routes.json`. Koordinaten sind **normiert**: `u` läuft von 0 bis 1 über die
Bildbreite, `v` von 0 bis 1 von oben nach unten. Ein Neu-Export des Panoramas in
anderer Auflösung macht das Topo dadurch nicht kaputt.

```jsonc
{
  "id": "steinerweg",
  "name": "Steinerweg",
  "color": "#ff5f3d",
  "grade": "VI-",            // UIAA
  "gradeObl": "V+",          // obligatorisch
  "lengthM": 800,
  "pitchCount": 18,
  "firstAscent": { "who": "...", "year": null },
  "character": "...", "protectionRating": "...", "gear": "...",
  "approach": "...", "descent": "...",
  "line":  [[0.598, 0.800], [0.601, 0.760]],   // die Kletterlinie
  "start": { "u": 0.598, "v": 0.800 },         // Einstieg
  "top":   { "u": 0.636, "v": 0.298 },         // Ausstieg
  "pitches": [
    { "n": 1, "grade": "IV", "lengthM": 50, "note": "Plattiger Einstieg",
      "belay": { "u": 0.601, "v": 0.762, "type": "2 BH" } }
  ],
  "protection": [
    { "type": "bolt", "u": 0.599, "v": 0.781, "pitch": 1 }
  ],
  "variants": [
    { "id": "...", "name": "...", "grade": "VI+", "note": "...", "line": [[...]] }
  ]
}
```

`protection.type` ist eines von `bolt` (Bohrhaken), `piton` (Schlaghaken),
`thread` (Sanduhr), `cam` (Klemmkeil oder Friend).

## Zeichenmodus

Knopf **Zeichnen** in der Kopfzeile, oder direkt <http://localhost:8080/?edit=1>.

Das ist das eigentliche Autorenwerkzeug. Linksklick setzt einen Punkt im gewählten
Modus, Rechtsklick löscht den nächstliegenden, `Cmd`/`Ctrl`+`Z` nimmt zurück,
`Esc` beendet den Modus.
*JSON kopieren* legt das fertige Routenobjekt in die Zwischenablage — von dort direkt
in `routes.json` einfügen und Grade, Längen und Notizen ergänzen. Bestehende Routen
sind im Zeichenmodus nicht anklickbar, damit sie nicht im Weg sind.

## Legende

| Symbol | Bedeutung |
|---|---|
| Steg mit zwei Ringen, nummeriert | Standplatz, mit Grad und Länge der Seillänge |
| gefüllter Punkt | Bohrhaken (BH) |
| Nagel mit Öhr | Schlaghaken, Normalhaken (NH) — Zustand prüfen |
| Sanduhr | Sanduhr (SU), Fädelstelle |
| Keil mit Drahtschlinge | Klemmkeil oder Friend empfohlen |
| Ring mit Abwärtspfeil | Abseilstand, Abseilpiste |
| Dreieck über Balken | Einstieg |
| Fähnchen | Ausstieg |
| Zelt | Biwakplatz |
| Warndreieck | Steinschlag, brüchiger Fels |
| durchgezogene Linie | Kletterlinie |
| Strichlinie | Variante, Quergang, Gehgelände, Band |
| Punktlinie | Zustieg, Abstieg |

Grade in UIAA (römisch). *obligat* ist der Grad, der ohne Ausruhen am Haken geklettert
werden muss.

## Aufbau

```
tools/
  extract_ridge.py           Silhouette aus einem Foto -> ridge_dachstein.json
  ridge_dachstein.json       Gratprofil der Südwand (aus Südwand.jpg)
  summits_dachstein.json     Gipfelnamen zu diesem Profil
  make_placeholder_wall.py   synthetische Kalkwand (nur für den Prototyp)
  make_artifact.py           kleinere Variante für die veröffentlichte Seite
  make_tiles.py              Großbild → Kachel-Pyramide + wall.json
  make_demo_routes.py        Demo-Routendaten
  serve.py                   Entwicklungsserver ohne Code-Cache
web/
  index.html
  css/app.css
  js/symbols.js   SVG-Symbole für Wand und Legende (eine Quelle für beides)
  js/app.js       Karte, Kachel-Layer, Koordinaten, Navigation
  js/topo.js      Routen zeichnen, Fokus-Modus, Detailansicht
  js/legend.js    Legende
  js/editor.js    Zeichenmodus
  data/wall.json     Bildgröße, Kachel-URL, Zoomstufen (erzeugt)
  data/summits.json  Gipfelnamen am Grat (erzeugt)
  data/routes.json   Routendaten (erzeugt bzw. von Hand gepflegt)
  tiles/             Bildkacheln (erzeugt)
```

Viewer ist [Leaflet](https://leafletjs.com) 1.9.4 mit `CRS.Simple` — dieselbe Technik
wie bei Landkarten, nur mit dem Wandbild statt einer Karte. Leaflet kommt aus dem CDN;
für einen Betrieb ohne Netz die beiden Dateien nach `web/vendor/` legen und die beiden
Verweise in `index.html` umbiegen.

## Darstellungsdetails, die bewusst so sind

- **Symbole skalieren gedämpft mit** (`--topo-scale`, Exponent 0,42). Die Linien kleben
  am Fels, aber die Strichstärke wächst beim Hineinzoomen nur langsam — sonst wird die
  Linie zum Balken und die Haken zu Tellern.
- **Standplatz-Fahnen wechseln links/rechts** und zeigen Grad und Länge erst ab einer
  gewissen Zoomstufe. Bei achtzehn Ständen auf einer Linie stapeln sie sich sonst.
- **Zwischensicherungen erscheinen erst beim Hineinzoomen.** In der Übersicht zeigt ein
  Topo nur Linien, sonst ist die Wand zugekleistert.
- **Panngrenze hängt am Zoom.** Die Wand ist 3:1 und damit flacher als ein übliches
  Fenster; eine feste Grenze würde beim Herauszoomen gegen das Einpassen arbeiten.
- **Zoomen zählt Rastungen, es misst sie nicht.** macOS beschleunigt Radereignisse
  stark; rechnet man wie Leaflet den zurückgelegten Radweg in Zoomstufen um, zoomt
  eine langsam gedrehte Rastung fast nicht und eine schnelle springt grob. Der Betrag
  von deltaY wird deshalb ignoriert. Schrittweiten: `STEP_SINGLE`, `STEP_STREAM`,
  `STEP_PINCH` in `web/js/app.js`.

  Leaflets Zoom-Animation bleibt dabei in Betrieb. Sie zu umgehen und den Zoom selbst
  Bild für Bild zu setzen wurde zweimal versucht und richtet zweierlei Schaden an: der
  Kachel-Layer baut dann bei jedem Bild sein Gitter neu auf (sichtbar als
  Schwarzwerden), und das Zoom-Ereignis feuert in jedem Bild, wodurch die
  Symbolskalierung zusätzlich zur Transformation der Vektorebene greift — die
  Routenlinien werden doppelt skaliert und verrutschen. **Nicht noch einmal versuchen,
  ohne vorher `updateScale` während der Geste stillzulegen.**

  Während einer laufenden Animation verwirft Leaflet jede weitere Zoom-Anfrage.
  Rastungen aus dieser Zeit werden deshalb aufaddiert und ein Bild nach dem Ende der
  Animation nachgezogen. Beim sehr schnellen Durchdrehen bleiben die Routenlinien an
  den Nahtstellen dieser Animationen kurz stehen — bekannt, bisher ungelöst.
- **Seillängen sind in beide Richtungen verknüpft.** Zeigen auf eine Tabellenzeile hebt
  den Standplatz in der Wand hervor, Zeigen auf einen Standplatz die Zeile — und
  scrollt sie bei Bedarf in den sichtbaren Bereich.
- **Im Zeichenmodus verschwindet die Routenliste.** Der frei werdende Platz geht
  automatisch an die Wand, weil die Ansicht ihre Ränder aus den tatsächlichen
  Panelbreiten berechnet.

## Wie die Platzhalter-Wand entsteht

`tools/make_placeholder_wall.py` modelliert die Wand als Tiefenrelief und beleuchtet
sie, statt nur Rauschen einzufärben. Die Bausteine:

0. **Silhouette aus einem echten Foto.** `tools/extract_ridge.py` liest den Grat gegen
   den Himmel aus `Südwand.jpg` aus und legt ihn als Zahlenreihe in
   `tools/ridge_dachstein.json` ab — nur das Höhenprofil, kein Bildinhalt. Der
   Generator setzt darauf die Wand auf. Dadurch stimmen Torstein, Mitterspitz und
   Hoher Dachstein in Lage und Verhältnis, und man erkennt die Wand sofort.
   Die Namen stehen in `tools/summits_dachstein.json` und landen mit Bildkoordinaten
   in `web/data/summits.json`, das die Website am Grat beschriftet.

   *Bildformat:* 2:1. Das Foto hat 1,58:1. Wird das Profil auf ein breiteres Format
   gestaucht, ohne die Höhe mitzuziehen, werden aus den Gipfeln flache Hügel —
   der Generator skaliert deshalb mit `span * Bildformat / Fotoformat`.

   *Grenze:* Das Foto endet östlich der Dirndl. Die Fortsetzung zum Koppenkarstein ist
   **geschätzt** und in `summits_dachstein.json` als `approx` markiert.

1. **Höhenfeld** — geriffeltes fraktales Rauschen mit Domain-Warping ergibt Pfeiler und
   Rinnen; hineingeschnitten werden Verschneidungen und **Schichtbänke**. Die
   horizontale Bankung ist das prägende Merkmal von Dachsteinkalk — reines Rauschen
   sieht ohne sie nie nach Kalkwand aus. Zusätzlich wird die Struktur an die
   Silhouette gekoppelt: unter den Gipfeln stehen Pfeiler, unter den Scharten ziehen
   Rinnen herunter. Ohne das wirkt die Silhouette aufgesetzt.
2. **Schlagschatten** — von jedem Punkt aus wird Richtung Sonne marschiert und geprüft,
   ob etwas davorsteht. Das bringt am meisten: die harten Schattenkanten unter
   Gesimsen und Überhängen entstehen nur so.
3. **Beleuchtung** — getrennt nach direktem Sonnenlicht (warm, gerichtet, durch den
   Schlagschatten unterbrochen) und Himmelslicht (kühl, diffus, durch
   Umgebungsverdeckung gedämpft). Deshalb sind die Schatten blau statt nur dunkel.
4. **Albedo** — Grundgestein, Wasserstreifen, Klüfte, Ockerpatina, Flechten, Schnee auf
   flachen Bändern, Blockschutt am Wandfuß.

Die Stellschrauben stehen als Konstanten oben in der Datei (Sonnenstand, Farben,
Anzahl der Schichtbänke, Zielneigung für die Normalen, Anteil der Bildbreite, den das
Foto abdeckt).

Für ein anderes Foto:

```bash
python3 tools/extract_ridge.py meinfoto.jpg --check work/ridge_check.jpg
python3 tools/make_placeholder_wall.py
python3 tools/make_tiles.py work/wall_placeholder.jpg
```

Das Kontrollbild zeigt die erkannte Linie über dem Foto. Sitzt sie falsch, hilft
`--blue-threshold` (kleiner = mehr gilt als Himmel).

## Was der Prototyp nicht kann

Kein Login, keine Routendatenbank, kein Redaktionssystem, kein Offline-Modus, keine
GPS-Position, kein echtes Stitching. Das sind Themen der richtigen Umsetzung.
