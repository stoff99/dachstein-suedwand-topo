/**
 * Topo-Layer: Routenlinien, Standplätze, Zwischensicherungen, Fokus-Modus.
 *
 * Geometrie kommt in normierten Koordinaten (u,v je 0..1) aus routes.json und wird
 * über uv2ll() in Leaflet-Koordinaten umgerechnet. Die Linien kleben damit am Fels,
 * ihre Strichstärke und die Symbolgröße skalieren beim Zoomen aber nur gedämpft mit
 * (siehe --topo-scale in app.js), sonst würde die Linie beim Hineinzoomen zum Balken.
 */

import { symbolSvg, SYMBOL_SHORT } from './symbols.js';

const PRO_ORDER = ['bolt', 'piton', 'thread', 'cam'];

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function lineWeight(scale) {
  return Math.max(2.0, Math.min(7.0, 2.5 * scale));
}

export function createTopo({ map, uv2ll, data, summits = [], maxNativeZoom,
                            onRouteClick, onPitchHover, getPadding }) {
  // Reihenfolge von links nach rechts in der Wand - danach richtet sich, ob der
  // Routenname über oder unter dem Einstieg sitzt.
  const byPosition = [...data.routes].sort((a, b) => a.start.u - b.start.u)
    .map((r) => r.id);
  const routes = data.routes.map((r) => buildRoute(r, byPosition.indexOf(r.id)));
  let active = null;
  let scale = 1;
  let proVisible = false;
  let activePitch = null;
  let hoverPitchN = null;

  // ------------------------------------------------------------------ Aufbau
  function buildRoute(r, index) {
    const latlngs = r.line.map(([u, v]) => uv2ll(u, v));
    const w = lineWeight(1);

    const casing = L.polyline(latlngs, {
      color: '#0b0e12', weight: w + 3.4, opacity: 0.55,
      lineCap: 'round', lineJoin: 'round', interactive: false,
    });
    const main = L.polyline(latlngs, {
      color: r.color, weight: w, opacity: 1,
      lineCap: 'round', lineJoin: 'round', interactive: false,
    });
    // Unsichtbare, breite Linie nur zum Anklicken - besonders auf dem Handy wichtig
    const hit = L.polyline(latlngs, {
      color: '#fff', weight: 22, opacity: 0, interactive: true, bubblingMouseEvents: false,
    });

    const label = L.marker(uv2ll(r.start.u, r.start.v), {
      interactive: true, keyboard: false, zIndexOffset: 400,
      icon: L.divIcon({
        className: 'topo-marker',
        iconSize: [0, 0], iconAnchor: [0, 0],
        // abwechselnd über und unter dem Einstieg, sonst überlappen sich die
        // Namen bei eng nebeneinander liegenden Routen
        html: `<span class="route-label ${index % 2 ? 'below' : ''}" style="--c:${r.color}">`
            + `${esc(r.name)} <em>${esc(r.grade)}</em></span>`,
      }),
    });

    const obj = {
      data: r,
      color: r.color,
      latlngs,
      bounds: L.latLngBounds(latlngs),
      casing, main, hit, label,
      overview: L.layerGroup([casing, main, hit, label]),
      detail: null, pro: null, variants: null,
      belayMarkers: new Map(),
      dim: false,
    };

    hit.on('click', (e) => { L.DomEvent.stop(e); onRouteClick?.(r.id); });
    label.on('click', (e) => { L.DomEvent.stop(e); onRouteClick?.(r.id); });
    hit.on('mouseover', () => setHover(obj, true));
    hit.on('mouseout', () => setHover(obj, false));
    return obj;
  }

  /** Standplätze, Einstieg und Ausstieg - erst beim ersten Fokus gebaut. */
  function ensureDetail(o) {
    if (o.detail) return;
    const r = o.data;
    const layers = [];

    layers.push(marker(r.start, 'start', o, 26, 500));
    layers.push(marker(r.top, 'top', o, 24, 500));

    for (const p of r.pitches) {
      // Fahnen wechselseitig links und rechts, sonst stapeln sie sich bei eng
      // liegenden Standplätzen übereinander und decken die Linie zu.
      const side = p.n % 2 ? 'side-right' : 'side-left';
      const m = L.marker(uv2ll(p.belay.u, p.belay.v), {
        interactive: true, keyboard: false, zIndexOffset: 600,
        icon: L.divIcon({
          className: `topo-marker belay-marker ${side}`,
          iconSize: [24, 24], iconAnchor: [12, 12],
          html: `<span class="belay-wrap" style="--c:${o.color};--tagline:${o.color}">`
              + symbolSvg('belay', o.color, 24)
              + `<span class="belay-tag"><b>${p.n}</b>`
              + `<i class="tag-detail">${esc(p.grade)} · ${p.lengthM} m</i></span>`
              + `</span>`,
        }),
      });
      m.on('click', (e) => { L.DomEvent.stop(e); highlightPitch(p.n, { fly: false }); });
      // Zeigen auf einen Standplatz hebt die Seillänge in der Tabelle hervor
      m.on('mouseover', () => hoverPitch(p.n));
      m.on('mouseout', () => hoverPitch(null));
      o.belayMarkers.set(p.n, m);
      layers.push(m);
    }

    o.detail = L.layerGroup(layers);
    o.pro = L.layerGroup(r.protection.map(
      (p) => marker(p, p.type, o, 20, 300, 'marker-pro')));

    o.variantCasings = [];
    o.variantMains = [];
    for (const v of r.variants || []) {
      const ll = v.line.map(([u, vv]) => uv2ll(u, vv));
      o.variantCasings.push(L.polyline(ll, {
        color: '#0b0e12', weight: lineWeight(scale) + 3, opacity: .5,
        dashArray: '10 8', interactive: false }));
      o.variantMains.push(L.polyline(ll, {
        color: o.color, weight: lineWeight(scale), opacity: .95,
        dashArray: '10 8', interactive: false }));
    }
    o.variants = L.layerGroup([...o.variantCasings, ...o.variantMains]);
  }

  function marker(pt, type, o, size, z, extraClass = '') {
    return L.marker(uv2ll(pt.u, pt.v), {
      interactive: false, keyboard: false, zIndexOffset: z,
      icon: L.divIcon({
        className: `topo-marker ${extraClass}`.trim(),
        iconSize: [size, size], iconAnchor: [size / 2, size / 2],
        html: symbolSvg(type, o.color, size),
      }),
    });
  }

  // ------------------------------------------------------------- Darstellung
  function applyStyles() {
    const w = lineWeight(scale);
    for (const o of routes) {
      o.main.setStyle({ weight: w, opacity: o.dim ? 0.16 : 1 });
      o.casing.setStyle({ weight: w + 3.4, opacity: o.dim ? 0.10 : 0.55 });
      const el = o.label.getElement();
      if (el) el.firstElementChild.classList.toggle('is-dim', o.dim);
      o.variantCasings?.forEach((l) => l.setStyle({ weight: w + 3 }));
      o.variantMains?.forEach((l) => l.setStyle({ weight: w }));
    }
  }

  function setHover(o, on) {
    if (o.dim) return;
    o.main.setStyle({ weight: lineWeight(scale) + (on ? 2.2 : 0) });
    if (on) { o.casing.bringToFront(); o.main.bringToFront(); }
  }

  function setScale(s) { scale = s; applyStyles(); }

  function setProVisible(v) {
    proVisible = v;
    if (!active) return;
    if (v) active.pro.addTo(map); else map.removeLayer(active.pro);
  }

  // ------------------------------------------------------------------ Fokus
  function focus(id, { fly = true } = {}) {
    const o = routes.find((x) => x.data.id === id);
    if (!o) return null;
    if (active && active !== o) hideDetail(active);

    active = o;
    activePitch = null;
    ensureDetail(o);
    routes.forEach((x) => { x.dim = x !== o; });
    applyStyles();

    hoverPitch(null);
    map.removeLayer(summitGroup);
    o.variants.addTo(map);
    o.detail.addTo(map);
    if (proVisible) o.pro.addTo(map);
    o.casing.bringToFront(); o.main.bringToFront();

    if (fly) map.flyToBounds(o.bounds, { ...getPadding(), maxZoom: maxNativeZoom, duration: 0.85 });
    return o;
  }

  function hideDetail(o) {
    [o.detail, o.pro, o.variants].forEach((g) => g && map.removeLayer(g));
  }

  function clear({ fly = true, bounds } = {}) {
    hoverPitch(null);
    if (active) hideDetail(active);
    summitGroup.addTo(map);
    active = null;
    activePitch = null;
    routes.forEach((x) => { x.dim = false; });
    applyStyles();
    if (fly && bounds) map.flyToBounds(bounds, { ...getPadding(), duration: 0.7 });
  }

  /**
   * Hervorhebung ohne Kamerafahrt, in beide Richtungen: Zeigen auf eine Tabellenzeile
   * hebt den Standplatz in der Wand hervor, Zeigen auf einen Standplatz die Zeile.
   *
   * Der Zustand liegt bewusst nur hier, und gemeldet wird unabhängig davon, woher der
   * Anstoß kam - sonst bleibt beim Wechsel zwischen Wand und Tabelle eine alte
   * Hervorhebung stehen. Eine Rückkopplung gibt es nicht: onPitchHover setzt nur
   * Klassen und scrollt, ruft aber nicht wieder hier herein.
   */
  function hoverPitch(n) {
    if (hoverPitchN === n) return;
    hoverPitchN = n;
    if (active) {
      for (const [num, m] of active.belayMarkers) {
        const el = m.getElement();
        if (!el) continue;
        el.classList.toggle('is-hover', num === n);
        m.setZIndexOffset(num === n ? 950 : (num === activePitch ? 900 : 600));
      }
    }
    onPitchHover?.(n);
  }

  function highlightPitch(n, { fly = true } = {}) {
    if (!active) return;
    activePitch = n;
    for (const [num, m] of active.belayMarkers) {
      m.getElement()?.classList.toggle('is-active', num === n);
      if (num === n) m.setZIndexOffset(900);
    }
    document.querySelectorAll('.pitch-row').forEach((tr) => {
      tr.classList.toggle('is-active', Number(tr.dataset.n) === n);
    });
    const p = active.data.pitches.find((x) => x.n === n);
    if (p && fly) {
      map.flyTo(uv2ll(p.belay.u, p.belay.v),
        Math.max(map.getZoom(), maxNativeZoom - 1.2), { duration: 0.6 });
    }
    return p;
  }

  // ------------------------------------------------- Zusammenfassung Material
  function proSummary(r, pitchN) {
    const counts = {};
    for (const p of r.protection) if (p.pitch === pitchN) counts[p.type] = (counts[p.type] || 0) + 1;
    return PRO_ORDER.filter((t) => counts[t])
      .map((t) => `${counts[t]}× ${SYMBOL_SHORT[t] || t}`).join(' · ');
  }

  function totals(r) {
    const counts = {};
    for (const p of r.protection) counts[p.type] = (counts[p.type] || 0) + 1;
    return PRO_ORDER.filter((t) => counts[t])
      .map((t) => `${counts[t]}× ${SYMBOL_SHORT[t] || t}`).join(' · ');
  }

  // ---------------------------------------------------------- Detail-Ansicht
  function detailHtml(o) {
    const r = o.data;
    const fa = r.firstAscent || {};
    const faText = [fa.who, fa.year].filter(Boolean).join(', ') || '—';

    const facts = [
      ['Schwierigkeit', `<b style="color:${r.color}">${esc(r.grade)}</b>`
        + (r.gradeObl ? ` <span class="muted">(obligat ${esc(r.gradeObl)})</span>` : '')],
      ['Wandhöhe', `${r.lengthM} m`],
      ['Seillängen', `${r.pitchCount}`],
      ['Erstbegehung', esc(faText)],
      ['Absicherung', esc(r.protectionRating)],
      ['Ausrichtung', esc(r.aspect)],
      ['Beste Zeit', esc(r.season)],
      ['Material im Topo', totals(r) || '—'],
    ];

    const variants = (r.variants || []).map((v) => `
      <div class="variant-card">
        <b>${esc(v.name)}</b> <span class="muted">${esc(v.grade)}</span>
        <p>${esc(v.note)}</p>
      </div>`).join('');

    const rows = r.pitches.map((p) => {
      const pro = proSummary(r, p.n);
      return `<tr class="pitch-row" data-n="${p.n}" style="--c:${r.color}">
        <td class="pitch-n">${p.n}</td>
        <td class="pitch-grade">${esc(p.grade)}</td>
        <td class="pitch-len">${p.lengthM} m</td>
        <td class="pitch-note">${esc(p.note)}
          <span class="pitch-belay">Stand: ${esc(p.belay.type)}${pro ? ` &nbsp;·&nbsp; ${pro}` : ''}</span>
        </td>
      </tr>`;
    }).join('');

    return {
      title: `<h2>${esc(r.name)}</h2>
              <p class="sub"><b style="color:${r.color}">${esc(r.grade)}</b> · ${r.lengthM} m · ${r.pitchCount} Seillängen</p>`,
      body: `
        ${data.placeholder ? `<p class="warn-box"><b>Platzhalterdaten.</b> Linienverlauf,
          Grade, Stände und Haken dieser Route sind frei erfunden und nicht zur
          Tourenplanung geeignet.</p>` : ''}
        <dl class="facts">${facts.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>
        <div class="detail-section"><h3>Charakter</h3><p>${esc(r.character)}</p></div>
        <div class="detail-section"><h3>Material</h3><p>${esc(r.gear)}</p></div>
        <div class="detail-section"><h3>Zustieg</h3><p>${esc(r.approach)}</p></div>
        <div class="detail-section"><h3>Abstieg</h3><p>${esc(r.descent)}</p></div>
        ${variants ? `<div class="detail-section"><h3>Varianten</h3></div>${variants}` : ''}
        <div class="detail-section"><h3>Seillängen</h3></div>
        <table class="pitch-table">
          <thead><tr><th>SL</th><th>Grad</th><th>Länge</th><th>Charakter und Absicherung</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>`,
    };
  }

  function listHtml() {
    return routes.map((o) => {
      const r = o.data;
      return `<li><button class="route-item" data-id="${esc(r.id)}" style="--c:${r.color}">
        <span class="route-swatch"></span>
        <span class="route-item-main">
          <span class="route-item-name">${esc(r.name)}</span>
          <span class="route-item-meta">${r.lengthM} m · ${r.pitchCount} SL · ${esc(r.protectionRating.split('.')[0])}</span>
        </span>
        <span class="route-grade">${esc(r.grade)}</span>
      </button></li>`;
    }).join('');
  }

  const allBounds = () => routes.reduce((b, o) => b.extend(o.bounds), L.latLngBounds(routes[0].latlngs));

  // Gipfelnamen am Grat. Sie machen auf einen Blick klar, welche Wand man vor sich
  // hat, stören aber in der Routenansicht - dort werden sie ausgeblendet.
  // nach Höhe sortiert: bei Platzmangel überlebt der wichtigere Gipfel
  const summitMarkers = [...summits]
    .sort((a, b) => (b.elevation || 0) - (a.elevation || 0))
    .map((s) => L.marker(uv2ll(s.u, s.v), {
    interactive: false, keyboard: false, zIndexOffset: 200,
    icon: L.divIcon({
      className: 'topo-marker',
      iconSize: [0, 0], iconAnchor: [0, 0],
      html: `<span class="summit-label"><b>${esc(s.name)}</b>`
          + (s.elevation ? `<i>${s.elevation} m</i>` : '') + `</span>`,
    }),
  }));
  const summitGroup = L.layerGroup(summitMarkers);

  /**
   * Beschriftungen entzerren.
   *
   * In der Übersicht auf einem Telefon ist die Wand nur gut dreihundert Pixel breit -
   * dann überlagern sich Gipfel- und Routennamen gegenseitig. Statt sie so klein zu
   * machen, dass sie niemand mehr liest, werden die weniger wichtigen ausgeblendet.
   * Beim Hineinzoomen kommen sie von selbst zurück, weil dann wieder Platz ist.
   *
   * Routennamen haben Vorrang vor Gipfelnamen, Gipfel untereinander nach Höhe.
   */
  function declutter() {
    const candidates = [];
    for (const o of routes) {
      const el = o.label.getElement()?.firstElementChild;
      if (!el) continue;
      el.classList.remove('is-crowded');
      if (!o.dim) candidates.push(el);
    }
    for (const m of summitMarkers) {
      const el = m.getElement()?.firstElementChild;
      if (!el) continue;
      el.classList.remove('is-crowded');
      candidates.push(el);
    }

    const view = map.getContainer().getBoundingClientRect();
    const taken = [];
    for (const el of candidates) {
      const r = el.getBoundingClientRect();
      if (!r.width) continue;
      // angeschnittene Beschriftungen sehen nach Fehler aus - lieber ganz weg
      const clipped = Math.max(0, view.left - r.left) + Math.max(0, r.right - view.right);
      if (clipped > 4) { el.classList.add('is-crowded'); continue; }
      const clash = taken.some((t) => r.left < t.right + 5 && r.right > t.left - 5
                                   && r.top < t.bottom + 3 && r.bottom > t.top - 3);
      if (clash) el.classList.add('is-crowded'); else taken.push(r);
    }
  }

  routes.forEach((o) => o.overview.addTo(map));
  summitGroup.addTo(map);

  return {
    routes, focus, clear, setScale, setProVisible, highlightPitch, hoverPitch, declutter,
    detailHtml, listHtml, allBounds, setHover,
    get active() { return active; },
    get activePitch() { return activePitch; },
    byId: (id) => routes.find((x) => x.data.id === id),
  };
}
