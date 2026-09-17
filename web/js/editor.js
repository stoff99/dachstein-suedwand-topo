/**
 * Zeichenmodus.
 *
 * Damit werden die Routendaten erzeugt: Linie klicken, Standplätze und Haken setzen,
 * JSON exportieren, in web/data/routes.json einfügen. Ausgegeben wird in normierten
 * Koordinaten (u,v je 0..1), damit das Topo einen Neu-Export des Panoramas übersteht.
 *
 *   Linksklick     Punkt im aktuellen Modus setzen
 *   Rechtsklick    nächstliegenden Punkt löschen
 *   Cmd/Ctrl+Z     letzten Schritt zurücknehmen
 *
 * Erreichbar über den Knopf "Zeichnen" in der Kopfzeile oder direkt mit ?edit=1.
 * initEditor() gibt eine Funktion zurück, die den Modus wieder vollständig abräumt.
 */

import { symbolSvg } from './symbols.js';

const MODES = [
  ['line', 'Linie'],
  ['belay', 'Standplatz'],
  ['bolt', 'Bohrhaken'],
  ['piton', 'Schlaghaken'],
  ['thread', 'Sanduhr'],
  ['cam', 'Klemmkeil'],
];

export function initEditor({ map, uv2ll, ll2uv, topo, showHint, aspect = 2, onClose }) {
  const state = { mode: 'line', color: '#ff2d95', name: 'Neue Route',
                  line: [], points: [], undo: [] };
  const layer = L.layerGroup().addTo(map);

  // Bestehende Routen dürfen die Klicks nicht abfangen: Klickflächen raus, und per
  // CSS-Klasse auch alle Beschriftungen und Symbole stummschalten.
  document.documentElement.classList.add('edit-mode');
  topo.routes.forEach((o) => map.removeLayer(o.hit));
  // Sonst löst schnelles Setzen zweier Punkte einen Doppelklick-Zoom aus.
  map.doubleClickZoom.disable();

  const box = document.createElement('aside');
  box.id = 'editor';
  box.innerHTML = `
    <div class="editor-head">
      <h3>Zeichenmodus</h3>
      <button class="btn btn-ghost editor-close" id="ed-close" type="button"
              aria-label="Zeichenmodus beenden">Fertig</button>
    </div>
    <p class="editor-stat">Linksklick setzt, Rechtsklick löscht den nächsten Punkt.</p>
    <div class="editor-modes">${MODES.map(([m, label]) =>
      `<button class="btn" data-mode="${m}">${label}</button>`).join('')}</div>
    <div class="editor-actions">
      <button class="btn" id="ed-undo">Rückgängig</button>
      <button class="btn" id="ed-clear">Leeren</button>
      <button class="btn btn-primary" id="ed-copy">JSON kopieren</button>
    </div>
    <p class="editor-stat" id="ed-stat"></p>
    <textarea id="ed-json" readonly spellcheck="false"></textarea>`;
  document.body.appendChild(box);

  const $e = (s) => box.querySelector(s);
  const modeButtons = [...box.querySelectorAll('[data-mode]')];

  function setMode(m) {
    state.mode = m;
    modeButtons.forEach((b) => b.classList.toggle('is-on', b.dataset.mode === m));
  }
  modeButtons.forEach((b) => b.addEventListener('click', () => setMode(b.dataset.mode)));
  setMode('line');

  // ---------------------------------------------------------------- Zeichnen
  function redraw() {
    layer.clearLayers();

    if (state.line.length > 1) {
      const ll = state.line.map(([u, v]) => uv2ll(u, v));
      L.polyline(ll, { color: '#0b0e12', weight: 7, opacity: .6, interactive: false }).addTo(layer);
      L.polyline(ll, { color: state.color, weight: 3.4, interactive: false }).addTo(layer);
    }
    for (const [u, v] of state.line) {
      L.circleMarker(uv2ll(u, v), {
        radius: 4, color: '#0b0e12', weight: 2, fillColor: state.color,
        fillOpacity: 1, interactive: false,
      }).addTo(layer);
    }
    let belayN = 0;
    for (const p of state.points) {
      const isBelay = p.type === 'belay';
      if (isBelay) belayN += 1;
      L.marker(uv2ll(p.u, p.v), {
        interactive: false,
        icon: L.divIcon({
          className: 'topo-marker',
          iconSize: [26, 26], iconAnchor: [13, 13],
          html: `<span class="belay-wrap" style="--c:${state.color};--tagline:${state.color}">`
              + symbolSvg(p.type, state.color, 26)
              + (isBelay ? `<span class="belay-tag"><b>${belayN}</b></span>` : '')
              + `</span>`,
        }),
      }).addTo(layer);
    }

    const belays = state.points.filter((p) => p.type === 'belay').length;
    $e('#ed-stat').textContent =
      `${state.line.length} Linienpunkte · ${belays} Standplätze · `
      + `${state.points.length - belays} Zwischensicherungen`;
    $e('#ed-json').value = exportJson();
  }

  function exportJson() {
    const r4 = (x) => Math.round(x * 1e4) / 1e4;
    let n = 0;
    const pitches = state.points.filter((p) => p.type === 'belay').map((p) => ({
      n: ++n, grade: '', lengthM: 0, note: '',
      belay: { u: r4(p.u), v: r4(p.v), type: '2 BH' },
    }));
    const protection = state.points.filter((p) => p.type !== 'belay').map((p) => ({
      type: p.type, u: r4(p.u), v: r4(p.v), pitch: null,
    }));
    return JSON.stringify({
      id: state.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'neue-route',
      name: state.name,
      color: state.color,
      grade: '', gradeObl: '', lengthM: 0, pitchCount: pitches.length,
      line: state.line.map(([u, v]) => [r4(u), r4(v)]),
      start: state.line.length ? { u: r4(state.line[0][0]), v: r4(state.line[0][1]) } : null,
      top: state.line.length ? { u: r4(state.line.at(-1)[0]), v: r4(state.line.at(-1)[1]) } : null,
      pitches, protection,
    }, null, 1);
  }

  function undoLast() {
    const last = state.undo.pop();
    if (!last) return;
    if (last.kind === 'line') state.line.pop(); else state.points.pop();
    redraw();
  }

  // ------------------------------------------------------------------ Klicks
  function onMapClick(e) {
    const [u, v] = ll2uv(e.latlng);
    if (u < 0 || u > 1 || v < 0 || v > 1) return;
    if (state.mode === 'line') {
      state.line.push([u, v]);
      state.undo.push({ kind: 'line' });
    } else {
      state.points.push({ type: state.mode, u, v });
      state.undo.push({ kind: 'point' });
    }
    redraw();
  }

  function onMapContext(e) {
    L.DomEvent.preventDefault(e);
    const [u, v] = ll2uv(e.latlng);
    // laengentreu: u zaehlt ueber die Breite, v ueber die Hoehe
    const d2 = (a, b) => ((a[0] - b[0]) * aspect) ** 2 + (a[1] - b[1]) ** 2;
    let best = null;
    state.line.forEach((p, i) => {
      const d = d2(p, [u, v]);
      if (!best || d < best.d) best = { d, kind: 'line', i };
    });
    state.points.forEach((p, i) => {
      const d = d2([p.u, p.v], [u, v]);
      if (!best || d < best.d) best = { d, kind: 'point', i };
    });
    if (!best || best.d > 0.0016) return;
    (best.kind === 'line' ? state.line : state.points).splice(best.i, 1);
    redraw();
  }

  function onKeyDown(e) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
      e.preventDefault();
      undoLast();
    }
  }

  map.on('click', onMapClick);
  map.on('contextmenu', onMapContext);
  document.addEventListener('keydown', onKeyDown);

  $e('#ed-undo').addEventListener('click', undoLast);
  $e('#ed-clear').addEventListener('click', () => {
    state.line = []; state.points = []; state.undo = [];
    redraw();
  });
  $e('#ed-copy').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(exportJson());
      showHint('Routen-JSON in der Zwischenablage.');
    } catch {
      $e('#ed-json').select();
      showHint('Kopieren im Browser blockiert — Text im Feld ist markiert.');
    }
  });
  $e('#ed-close').addEventListener('click', () => onClose?.());

  redraw();
  showHint('Zeichenmodus aktiv. Bestehende Routen sind hier nicht anklickbar.', 5000);

  /** Räumt den Modus vollständig ab und stellt die normale Bedienung wieder her. */
  return function destroy() {
    map.off('click', onMapClick);
    map.off('contextmenu', onMapContext);
    document.removeEventListener('keydown', onKeyDown);
    map.removeLayer(layer);
    box.remove();
    map.doubleClickZoom.enable();
    topo.routes.forEach((o) => o.hit.addTo(map));
    document.documentElement.classList.remove('edit-mode');
  };
}
