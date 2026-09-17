/**
 * Legende. Verwendet dieselben Symbolfunktionen wie die Wand, damit Karte und
 * Legende nicht auseinanderlaufen können.
 */

import { symbolSvg, lineSampleSvg, SYMBOL_LABELS } from './symbols.js';

const NEUTRAL = '#dfe7f1';

const GROUPS = [
  {
    title: 'Sicherungspunkte',
    items: ['belay', 'bolt', 'piton', 'thread', 'cam', 'rappel'],
  },
  {
    title: 'Linien',
    lines: [
      ['solid', 'Kletterlinie', 'die eigentliche Route'],
      ['dashed', 'Variante / Quergang', 'auch Gehgelände und Bänder'],
      ['dotted', 'Zustieg / Abstieg', 'nicht geklettert'],
    ],
  },
  {
    title: 'Weitere Zeichen',
    items: ['start', 'top', 'bivouac', 'danger'],
  },
];

export function renderLegend(el) {
  const groups = GROUPS.map((g) => {
    const rows = g.lines
      ? g.lines.map(([style, name, note]) => row(lineSampleSvg(style, NEUTRAL), name, note))
      : g.items.map((t) => {
        const [name, note] = SYMBOL_LABELS[t] || [t, ''];
        return row(symbolSvg(t, NEUTRAL, 26), name, note);
      });
    return `<div class="legend-group"><h4>${g.title}</h4>${rows.join('')}</div>`;
  }).join('');

  el.innerHTML = groups + `
    <div class="legend-group">
      <h4>Grade</h4>
      <p class="small muted" style="margin:0">
        Schwierigkeit in UIAA (römisch, III bis VII). <b>obligat</b> ist der Grad,
        der ohne Ausruhen am Haken geklettert werden muss. Farbe und Nummer eines
        Standplatzes gehören zur jeweiligen Route.
      </p>
    </div>`;
}

function row(sym, name, note) {
  return `<div class="legend-row">
    <span class="sym-cell">${sym}</span>
    <span><b>${name}</b><span>${note}</span></span>
  </div>`;
}

/**
 * Die Legende hängt als Blatt unter ihrem Knopf in der Kopfzeile und startet
 * geschlossen: sie ist ein Nachschlagewerk und soll die Wand nicht zudecken.
 */
export function initLegend({ box, button, close, body }) {
  renderLegend(body);

  function setOpen(on) {
    box.hidden = !on;
    button.classList.toggle('is-on', on);
    button.setAttribute('aria-pressed', String(on));
  }

  button.addEventListener('click', () => setOpen(box.hidden));
  close.addEventListener('click', () => setOpen(false));
  setOpen(false);

  return { setOpen, isOpen: () => !box.hidden };
}
