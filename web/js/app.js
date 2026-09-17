/**
 * Einstiegspunkt der Topo-Website.
 *
 * Aufbau
 *   wall.json    Bildgröße, Kachel-URL, Zoomstufen  (von tools/make_tiles.py erzeugt)
 *   routes.json  Routen in normierten Koordinaten   (von tools/make_demo_routes.py
 *                bzw. später aus dem Zeichenmodus)
 *
 * Das Bild liegt als Kachel-Pyramide vor. Leaflet mit CRS.Simple behandelt es wie eine
 * Karte: es lädt immer nur die Kacheln, die gerade sichtbar sind, und skaliert über
 * maxNativeZoom hinaus hoch. Die Routen werden in Bildkoordinaten verankert, ihre
 * Darstellungsgröße hängt an --topo-scale.
 */

import { createTopo } from './topo.js';
import { initLegend } from './legend.js';

const $ = (sel) => document.querySelector(sel);
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const isMobile = () => window.matchMedia('(max-width: 860px)').matches;

const els = {
  map: $('#map'),
  panel: $('#panel'),
  viewList: $('#view-list'),
  viewDetail: $('#view-detail'),
  routeList: $('#route-list'),
  routeCount: $('#route-count'),
  detailTitle: $('#detail-title'),
  detailBody: $('#detail-body'),
  hint: $('#hint'),
  wallName: $('#wall-name'),
  wallSub: $('#wall-sub'),
};

let hintTimer = null;
function showHint(text, ms = 3600) {
  els.hint.textContent = text;
  els.hint.hidden = false;
  clearTimeout(hintTimer);
  hintTimer = setTimeout(() => { els.hint.hidden = true; }, ms);
}

async function boot() {
  const [wall, data, summitDoc] = await Promise.all([
    fetch('data/wall.json').then((r) => r.json()),
    fetch('data/routes.json').then((r) => r.json()),
    // optional: fehlt die Datei, bleibt der Grat eben unbeschriftet
    fetch('data/summits.json').then((r) => (r.ok ? r.json() : null)).catch(() => null),
  ]);
  const img = wall.image;
  const Z = img.maxNativeZoom;

  // ------------------------------------------------------------------ Karte
  const map = L.map('map', {
    crs: L.CRS.Simple,
    minZoom: 0,
    maxZoom: img.maxZoom ?? Z + 3,
    zoomSnap: 0,        // damit fitBounds exakt einpasst, nicht auf Stufen rastet
    zoomDelta: 1,
    zoomControl: false,
    attributionControl: false,
  });

  /** normierte Bildkoordinate -> Leaflet-Koordinate */
  const uv2ll = (u, v) => map.unproject([u * img.width, v * img.height], Z);
  /** Leaflet-Koordinate -> normierte Bildkoordinate */
  const ll2uv = (ll) => {
    const p = map.project(ll, Z);
    return [p.x / img.width, p.y / img.height];
  };

  const bounds = L.latLngBounds(uv2ll(0, 1), uv2ll(1, 0));

  const tiles = L.tileLayer(img.tileUrl, {
    tileSize: img.tileSize,
    minZoom: 0,
    maxNativeZoom: Z,
    maxZoom: img.maxZoom ?? Z + 3,
    bounds,
    noWrap: true,
    keepBuffer: 3,
  }).addTo(map);

  /**
   * Sichtbarer Bereich abzüglich Kopfzeile, Panel und Legende. Danach richten sich
   * sowohl die Gesamtansicht als auch das Heranfliegen an eine Route.
   */
  function viewPadding() {
    const panel = els.panel;
    const editor = document.getElementById('editor');   // nur im Zeichenmodus da
    let tl, br;
    if (isMobile()) {
      const collapsed = document.body.classList.contains('sheet-collapsed');
      const sheet = editor ? editor.offsetHeight
        : (collapsed ? 56 : (panel?.offsetHeight || 0));
      // oben Platz für Kopfzeile und Gipfelnamen, unten für Panel oder Werkzeug
      tl = [26, 104];
      br = [26, sheet + 16];
    } else {
      tl = [editor ? editor.offsetWidth + 24 : 40, 112];
      br = [(panel?.offsetWidth || 0) + 40, 40];
    }
    // Auf sehr kleinen Flächen - ausgeblendeter Bereich, schmales Fenster - darf der
    // Rand nicht größer werden als die Fläche selbst. Sonst rechnet Leaflet mit
    // negativer Größe und liefert NaN als Zoomstufe und Mittelpunkt.
    const size = map.getSize();
    const squeeze = (a, b, total) => {
      const max = Math.max(total * 0.7, 1);
      const sum = a + b;
      return sum > max ? [a * max / sum, b * max / sum] : [a, b];
    };
    const [l, r] = squeeze(tl[0], br[0], size.x);
    const [t, b] = squeeze(tl[1], br[1], size.y);
    return { paddingTopLeft: [l, t], paddingBottomRight: [r, b] };
  }
  const paddingSum = () => {
    const p = viewPadding();
    return L.point(p.paddingTopLeft[0] + p.paddingBottomRight[0],
                   p.paddingTopLeft[1] + p.paddingBottomRight[1]);
  };
  /** Hat die Karte überhaupt eine Fläche? Ohne die ist jede Einpassung sinnlos. */
  const hasArea = () => map.getSize().x > 20 && map.getSize().y > 20;

  /**
   * Panngrenze: die Wand darf nicht aus dem Blick geschoben werden.
   *
   * Leaflets eingebautes maxBounds ist dafür unbrauchbar. Es rückt die Karte aus dem
   * laufenden Ereignis heraus sofort zurück und bricht damit eine Zoom-Animation ab.
   * Danach verschluckt Leaflet jede weitere Zoom-Anfrage, weil sein internes
   * Animationsflag gesetzt bleibt — das Zoomen reagiert dann gar nicht mehr.
   *
   * Stattdessen wird am Ende einer Bewegung geprüft und notfalls sanft zurückgeholt.
   * Der erlaubte Rand wächst mit der Fenstergröße in Kartenkoordinaten, also
   * umgekehrt proportional zum Zoom: ein fester Rand würde beim Herauszoomen gegen
   * das Einpassen arbeiten, weil die Wand mit 2:1 flacher ist als ein übliches
   * Fenster.
   */
  let recentering = false;
  map.on('moveend', () => {
    // Während einer Radgeste nicht eingreifen - das Zurückholen würde mitten in die
    // Geste hineinfahren. Am Ende der Geste greift es ganz normal.
    if (recentering || wheel.busy || wheel.queued) return;
    const size = map.getSize();
    const perUnit = Math.pow(2, map.getZoom());       // Bildschirmpixel je Karteneinheit
    const mLat = (size.y / perUnit) * 0.35;
    const mLng = (size.x / perUnit) * 0.35;
    const c = map.getCenter();
    const lat = clamp(c.lat, bounds.getSouth() - mLat, bounds.getNorth() + mLat);
    const lng = clamp(c.lng, bounds.getWest() - mLng, bounds.getEast() + mLng);
    if (lat === c.lat && lng === c.lng) return;
    recentering = true;
    map.once('moveend', () => { recentering = false; });
    map.panTo([lat, lng], { animate: true, duration: 0.35 });
  });
  // Bezugszoom = Zoomstufe, bei der die ganze Wand ins Bild passt. Daran hängt die
  // Größe der Topo-Symbole, deshalb muss er sich bei jeder Größenänderung mitziehen.
  let fitZoom = hasArea() ? map.getBoundsZoom(bounds, false, paddingSum()) : 1;
  let proMinZoom = fitZoom + 2.0;
  let userMoved = false;
  let shownId = null;          // welche Route gerade dargestellt ist
  let wantedId = null;         // welche Route dargestellt werden soll
  let editorDestroy = null;    // gesetzt, solange der Zeichenmodus läuft

  // Zustand des Mausrad-Zooms, siehe "Zoom per Rad" weiter unten
  const wheel = {
    queued: null,   // { zoom, point } - wartet auf die laufende Zoom-Animation
    busy: false,    // läuft gerade eine Zoom-Animation?
    timer: null,
    seen: 0,
    done: 0,
  };

  // Immer erst eine gültige Ansicht setzen. Ist der Bereich gerade ausgeblendet, hat
  // die Karte keine Fläche - dann wird nur grob positioniert und später nachgezogen.
  map.setView(bounds.getCenter(), fitZoom, { animate: false });
  if (hasArea()) map.fitBounds(bounds, { ...viewPadding(), animate: false });

  // ------------------------------------------------------------ Kopfzeile
  const meta = wall.meta || {};
  if (meta.name) els.wallName.textContent = meta.name;
  if (meta.subtitle) els.wallSub.textContent = meta.subtitle;
  if (meta.placeholder || data.placeholder) {
    // Der Hinweis steht im Info-Fenster und bei jeder Route im Detail - in der
    // Kopfzeile lag er über dem Logo.
    const box = $('#info-placeholder');
    box.hidden = false;
    box.innerHTML = '<b>Prototyp mit Platzhalterdaten.</b> Das Wandbild ist synthetisch '
      + 'erzeugt, sämtliche Routenlinien, Grade, Stände und Haken sind frei erfunden. '
      + 'Nicht zur Tourenplanung geeignet.';
  }

  // ------------------------------------------------------------------ Topo
  const topo = createTopo({ map, uv2ll, data, maxNativeZoom: Z,
    summits: summitDoc?.summits || [],
    onRouteClick: (id) => goRoute(id),
    onPitchHover: (n) => highlightPitchRow(n),
    getPadding: viewPadding });

  /**
   * Gegenstück zum Zeigen auf einen Standplatz in der Wand: die zugehörige Zeile in
   * der Seillängen-Tabelle hervorheben und, falls sie außerhalb des sichtbaren
   * Bereichs liegt, sanft hinscrollen.
   */
  function highlightPitchRow(n) {
    let row = null;
    els.detailBody.querySelectorAll('.pitch-row').forEach((tr) => {
      const on = Number(tr.dataset.n) === n;
      tr.classList.toggle('is-hover', on);
      if (on) row = tr;
    });
    if (!row) return;

    const box = els.detailBody.getBoundingClientRect();
    const r = row.getBoundingClientRect();
    const margin = 28;
    let delta = 0;
    if (r.top < box.top + margin) delta = r.top - box.top - margin;
    else if (r.bottom > box.bottom - margin) delta = r.bottom - box.bottom + margin;
    if (delta) els.detailBody.scrollBy({ top: delta, behavior: 'smooth' });
  }

  els.routeList.innerHTML = topo.listHtml();
  els.routeCount.textContent = `${data.routes.length} Routen in dieser Wand`;

  // --------------------------------------------- Maßstab der Topo-Symbole
  // Gedämpfte Mitskalierung: der Exponent 0.42 sorgt dafür, dass Symbole beim
  // Hineinzoomen wachsen, aber nie die Wand zukleistern.
  function updateScale() {
    const z = map.getZoom();
    const s = clamp(Math.pow(2, (z - fitZoom) * 0.42), 0.62, 1.45);
    document.documentElement.style.setProperty('--topo-scale', s.toFixed(3));
    topo.setScale(s);
    topo.setProVisible(z >= proMinZoom);
    // Grad und Länge an den Standplätzen erst, wenn wirklich Platz dafür ist
    document.documentElement.classList.toggle('topo-detail', z >= fitZoom + 3.0);
  }
  map.on('zoom zoomend', updateScale);
  // Beschriftungen erst nach der Bewegung entzerren - das misst im Baum und soll
  // nicht in jedem Bild laufen.
  map.on('zoomend', () => topo.declutter());
  updateScale();
  requestAnimationFrame(() => topo.declutter());

  // Der Browserbereich kann nach dem Laden noch wachsen (Fenster, Panel, Drehung des
  // Handys). Dann neu vermessen - und solange der Nutzer nichts angefasst hat, die
  // Gesamtansicht neu einpassen.
  els.map.addEventListener('pointerdown', () => { userMoved = true; });

  let resizeTimer = null;
  function handleResize() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      map.invalidateSize({ animate: false });
      if (!hasArea()) return;
      fitZoom = map.getBoundsZoom(bounds, false, paddingSum());
      proMinZoom = fitZoom + 2.0;
      if (!shownId && !userMoved) map.fitBounds(bounds, { ...viewPadding(), animate: false });
      updateScale();
      topo.declutter();
    }, 80);
  }

  // Referenz festhalten, sonst darf der Browser den Beobachter wegräumen.
  const mapResizeObserver = new ResizeObserver(handleResize);
  mapResizeObserver.observe(els.map);
  window.addEventListener('resize', handleResize);
  window.addEventListener('orientationchange', handleResize);
  handleResize();

  // ------------------------------------------------------- Navigation
  function render() {
    stopWheelZoom();            // nicht gegen ein programmgesteuertes Anfliegen arbeiten
    const id = wantedId;
    const route = id && topo.byId(id);

    if (route) {
      els.viewList.hidden = true;
      els.viewDetail.hidden = false;
      if (shownId !== id) {
        const html = topo.detailHtml(route);
        els.detailTitle.innerHTML = html.title;
        els.detailBody.innerHTML = html.body;
        els.detailBody.scrollTop = 0;
        if (isMobile()) document.body.classList.remove('sheet-collapsed');
        topo.focus(id);
        // Erst nach dem Heranfliegen beurteilen, ob noch Zoom fehlt
        map.once('moveend', () => {
          if (map.getZoom() < proMinZoom) {
            showHint('Weiter hineinzoomen — dann erscheinen Haken und Sanduhren.');
          }
        });
      }
      shownId = id;
    } else {
      els.viewDetail.hidden = true;
      els.viewList.hidden = false;
      if (shownId !== null) topo.clear({ fly: true, bounds });
      shownId = null;
    }
  }

  // Die Adresszeile ist Komfort, nicht Wahrheit: in einem eingebetteten Rahmen oder
  // unter file:// wirft pushState. Der Zustand liegt deshalb in wantedId, die URL wird
  // nur mitgeführt, solange der Browser das zulässt.
  function urlRouteId() {
    try { return decodeURIComponent(location.hash.slice(1)) || null; } catch { return null; }
  }
  function pushUrl(id) {
    try {
      const base = location.pathname + location.search;
      history.pushState({ route: id }, '', id ? `${base}#${encodeURIComponent(id)}` : base);
    } catch { /* eingebettet oder file:// - dann eben ohne Adresszeile */ }
  }

  function goRoute(id) {
    if (wantedId === id) return;
    wantedId = id;
    pushUrl(id);
    render();
  }
  function goList() {
    if (!wantedId) return;
    wantedId = null;
    pushUrl(null);
    render();
  }

  window.addEventListener('popstate', () => { wantedId = urlRouteId(); render(); });

  els.routeList.addEventListener('click', (e) => {
    const btn = e.target.closest('.route-item');
    if (btn) goRoute(btn.dataset.id);
  });
  els.routeList.addEventListener('mouseover', (e) => {
    const btn = e.target.closest('.route-item');
    if (btn) topo.setHover(topo.byId(btn.dataset.id), true);
  });
  els.routeList.addEventListener('mouseout', (e) => {
    const btn = e.target.closest('.route-item');
    if (btn) topo.setHover(topo.byId(btn.dataset.id), false);
  });

  els.detailBody.addEventListener('click', (e) => {
    const tr = e.target.closest('.pitch-row');
    if (tr) topo.highlightPitch(Number(tr.dataset.n));
  });
  // Zeigen auf eine Zeile hebt den Standplatz in der Wand hervor - ohne Kamerafahrt,
  // sonst würde die Karte beim bloßen Überfahren der Tabelle herumspringen.
  els.detailBody.addEventListener('mouseover', (e) => {
    const tr = e.target.closest('.pitch-row');
    topo.hoverPitch(tr ? Number(tr.dataset.n) : null);
  });
  els.detailBody.addEventListener('mouseleave', () => topo.hoverPitch(null));

  $('#btn-back').addEventListener('click', goList);
  $('#btn-reset').addEventListener('click', () => {
    stopWheelZoom();
    goList();
    map.flyToBounds(bounds, { ...viewPadding(), duration: 0.7 });
  });

  const legend = initLegend({
    box: $('#legend'), button: $('#btn-legend'),
    close: $('#legend-close'), body: $('#legend-body'),
  });

  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || $('#info-dialog').open) return;
    if (legend.isOpen()) legend.setOpen(false);
    else if (editorDestroy) setEditMode(false);
    else goList();
  });

  // ------------------------------------------------------------ Zoom per Rad
  /**
   * Zoomen mit dem Mausrad.
   *
   * 1. **Rastungen werden gezählt, nicht gemessen.** macOS beschleunigt
   *    Radereignisse stark: rechnet man wie Leaflet den zurückgelegten Radweg in
   *    Zoomstufen um, zoomt eine langsam gedrehte Rastung fast nicht und eine
   *    schnelle springt grob. Der Betrag von deltaY wird deshalb ignoriert.
   *
   * 2. **Leaflets Zoom-Animation bleibt in Betrieb.** Sie zu umgehen und den Zoom
   *    selbst Bild für Bild zu setzen bringt zwei Schäden: der Kachel-Layer baut dann
   *    bei jedem Bild sein Gitter neu auf (sichtbar als Schwarzwerden), und das
   *    Zoom-Ereignis feuert in jedem Bild, wodurch die Symbolskalierung weiter unten
   *    zusätzlich zur Transformation der Vektorebene greift - die Routenlinien werden
   *    dann doppelt skaliert und verrutschen.
   *
   * 3. **Rastungen während einer laufenden Animation gehen nicht verloren.** Leaflet
   *    verwirft in dieser Zeit jede Zoom-Anfrage. Sie werden deshalb aufaddiert und
   *    ein Bild nach dem Ende der Animation nachgezogen - das eine Bild Abstand gibt
   *    Leaflet Zeit, Kachelgitter und Vektorebene zu setzen, bevor die nächste
   *    Animation beginnt.
   */
  const WHEEL_COOLDOWN = 55;   // ms Sperrzeit zwischen zwei gezählten Rastungen
  const WHEEL_IDLE = 200;      // ab dieser Pause gilt eine Rastung als einzeln
  const NOTCH_PX = 120;        // üblicher deltaY-Wert einer Rastung
  const ZOOM_GUARD = 340;      // ms Notbremse, falls zoomend einmal ausbleibt

  // Schrittweiten. Eine Zoomstufe ist Faktor 2 - Kartendienste nehmen dafür eine
  // ganze Stufe je Rastung, für ein Foto ist das zu grob, weil man Details anschaut.
  // Hier zum Nachjustieren an einer Stelle:
  const STEP_SINGLE = 0.45;    // Zoomstufen bei einzelner Rastung (Faktor ~1,37)
  const STEP_STREAM = 0.22;    // Zoomstufen beim Durchdrehen
  const STEP_PINCH = 0.16;     // Trackpad-Pinch meldet sich als Rad mit Strg

  map.scrollWheelZoom.disable();

  function stopWheelZoom() {
    clearTimeout(wheel.timer);
    wheel.timer = null;
    wheel.queued = null;
  }

  function flushZoom() {
    if (!wheel.queued || wheel.busy) return;
    const { zoom, point } = wheel.queued;
    wheel.queued = null;
    if (Math.abs(zoom - map.getZoom()) < 0.005) return;
    wheel.busy = true;
    clearTimeout(wheel.timer);
    wheel.timer = setTimeout(zoomIdle, ZOOM_GUARD);
    map.setZoomAround(point, zoom, { animate: true });
  }

  function zoomIdle() {
    clearTimeout(wheel.timer);
    wheel.timer = null;
    wheel.busy = false;
    // ein Bild Abstand: erst Kachelgitter und Vektorebene setzen lassen
    if (wheel.queued) requestAnimationFrame(flushZoom);
  }

  map.on('zoomend', zoomIdle);

  // Im Hintergrund laufen keine Animationen. Ein noch offener Schritt würde beim
  // Zurückwechseln auf einen Schlag zuschlagen - deshalb verwerfen.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') stopWheelZoom();
  });

  els.map.addEventListener('wheel', (e) => {
    e.preventDefault();
    userMoved = true;
    const now = e.timeStamp || performance.now();
    const isolated = now - wheel.seen > WHEEL_IDLE;
    wheel.seen = now;
    if (!isolated && now - wheel.done < WHEEL_COOLDOWN) return;
    wheel.done = now;

    // Der Betrag wird bewusst ignoriert - mit einer Ausnahme: manche Browser fassen
    // mehrere Rastungen zu einem Ereignis zusammen. Bei einer einzelnen Rastung darf
    // ein großer Wert deshalb bis zu drei Schritte auslösen, mehr nicht.
    let step = e.ctrlKey ? STEP_PINCH : (isolated ? STEP_SINGLE : STEP_STREAM);
    if (isolated && !e.ctrlKey) {
      step *= clamp(Math.round(Math.abs(e.deltaY) / NOTCH_PX), 1, 3);
    }

    const base = wheel.queued ? wheel.queued.zoom : map.getZoom();
    wheel.queued = {
      zoom: clamp(base + (e.deltaY > 0 ? -step : step),
                  map.getMinZoom(), map.getMaxZoom()),
      // auf den Mauszeiger zoomen, nicht auf die Bildmitte
      point: map.mouseEventToContainerPoint(e),
    };
    flushZoom();
  }, { passive: false });

  // ---------------------------------------------------------- Bedienelemente
  $('#btn-zoom-in').addEventListener('click', () => { userMoved = true; map.zoomIn(); });
  $('#btn-zoom-out').addEventListener('click', () => { userMoved = true; map.zoomOut(); });

  const dlg = $('#info-dialog');
  $('#btn-info').addEventListener('click', () => dlg.showModal());
  $('#info-close').addEventListener('click', () => dlg.close());
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });

  $('#sheet-handle').addEventListener('click', () => {
    document.body.classList.toggle('sheet-collapsed');
  });


  if (isMobile()) document.body.classList.add('sheet-collapsed');

  // ---------------------------------------------------------------- Fertig
  const done = () => document.body.classList.add('is-ready');
  tiles.once('load', done);
  setTimeout(done, 2500);

  wantedId = urlRouteId();     // Direktlink auf eine Route
  render();

  // ------------------------------------------------------------ Zeichenmodus
  // Wird erst beim Einschalten geladen - im normalen Betrieb kostet er nichts.
  const btnEdit = $('#btn-edit');
  const btnEditLabel = $('#btn-edit-label');

  async function setEditMode(on) {
    if (on === !!editorDestroy) return;
    // Wer schon in die Wand hineingezoomt hat, will beim Umschalten nicht wieder
    // herausgerissen werden. Nur aus der Gesamtansicht heraus neu einpassen.
    const wasOverview = map.getZoom() <= fitZoom + 0.35;

    if (on) {
      goList();
      const { initEditor } = await import('./editor.js');
      editorDestroy = initEditor({
        map, uv2ll, ll2uv, topo, showHint,
        aspect: img.width / img.height,
        onClose: () => setEditMode(false),
      });
    } else {
      editorDestroy();
      editorDestroy = null;
    }
    btnEdit.classList.toggle('is-on', on);
    btnEdit.setAttribute('aria-pressed', String(on));
    btnEditLabel.textContent = on ? 'Fertig' : 'Zeichnen';

    // Der freie Platz hat sich geändert: Bezugszoom nachziehen, Ansicht anpassen.
    requestAnimationFrame(() => {
      if (!hasArea()) return;
      fitZoom = map.getBoundsZoom(bounds, false, paddingSum());
      proMinZoom = fitZoom + 2.0;
      if (wasOverview) map.flyToBounds(bounds, { ...viewPadding(), duration: 0.5 });
      updateScale();
    });
  }

  btnEdit.addEventListener('click', () => setEditMode(!editorDestroy));
  if (new URLSearchParams(location.search).get('edit') === '1') setEditMode(true);

  // für die Konsole und den Zeichenmodus
  window.TOPO = { map, topo, uv2ll, ll2uv, img, bounds, wall, data };
}

boot().catch((err) => {
  console.error(err);
  document.body.classList.add('is-ready');
  document.body.insertAdjacentHTML('beforeend',
    `<div class="hint" style="max-width:min(520px,90vw);white-space:normal;text-align:center">
       <b>Die Wand konnte nicht geladen werden.</b><br>${String(err)}<br>
       <span class="muted small">Die Seite muss über einen Webserver laufen, nicht über file://
       — zum Beispiel <code>python3 -m http.server -d web 8080</code></span>
     </div>`);
});
