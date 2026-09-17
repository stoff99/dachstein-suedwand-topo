/**
 * Topo-Symbole als Inline-SVG.
 *
 * Alle Glyphen leben im Koordinatensystem 0..24 mit dem Mittelpunkt bei (12,12).
 * Jedes Symbol wird zweimal gezeichnet: erst eine dunkle Kontur, darüber die
 * Routenfarbe. Nur so bleiben die Zeichen auf hellem Kalk und in dunklen Rinnen
 * gleichermaßen lesbar.
 *
 * Dieselben Funktionen liefern die Symbole für die Wand UND für die Legende,
 * damit beides nicht auseinanderlaufen kann.
 */

export const INK = '#0b0e12';

const GLYPHS = {
  // Bohrhaken: gefüllter Punkt mit dunklem Rand
  bolt: (c) => `
    <circle cx="12" cy="12" r="6.4" fill="${INK}"/>
    <circle cx="12" cy="12" r="4.3" fill="${c}"/>`,

  // Schlaghaken / Normalhaken: Nagel mit Öhr, schräg geschlagen
  piton: (c) => `
    <g transform="rotate(-38 12 12)">
      <path d="M8 12 H19.5" stroke="${INK}" stroke-width="6" stroke-linecap="round"/>
      <path d="M8 12 H19.5" stroke="${c}" stroke-width="2.6" stroke-linecap="round"/>
      <circle cx="7.4" cy="12" r="4.4" fill="${INK}"/>
      <circle cx="7.4" cy="12" r="2.8" fill="${c}"/>
      <circle cx="7.4" cy="12" r="1.2" fill="${INK}"/>
    </g>`,

  // Sanduhr: zwei Dreiecke Spitze auf Spitze
  thread: (c) => `
    <path d="M6.4 4.6 H17.6 L12 12 Z M6.4 19.4 H17.6 L12 12 Z"
          fill="${c}" stroke="${INK}" stroke-width="2.4" stroke-linejoin="round"/>`,

  // Klemmkeil / Friend: Keil mit Drahtschlinge, steht für mobile Sicherung
  cam: (c) => `
    <path d="M12 13 V20.6" stroke="${INK}" stroke-width="5.4" stroke-linecap="round"/>
    <path d="M12 13 V20.6" stroke="${c}" stroke-width="2.2" stroke-linecap="round"/>
    <path d="M6.6 5.2 H17.4 L14.2 13.6 H9.8 Z" fill="${c}" stroke="${INK}"
          stroke-width="2.4" stroke-linejoin="round"/>`,

  // Standplatz: Anker-Steg mit zwei Ringen, quer zur Linie
  belay: (c) => `
    <rect x="1.4" y="9.4" width="21.2" height="5.2" rx="2.6" fill="${INK}"/>
    <rect x="2.9" y="10.6" width="18.2" height="2.8" rx="1.4" fill="${c}"/>
    <circle cx="7.2" cy="12" r="3.5" fill="${INK}"/>
    <circle cx="7.2" cy="12" r="1.8" fill="${c}"/>
    <circle cx="16.8" cy="12" r="3.5" fill="${INK}"/>
    <circle cx="16.8" cy="12" r="1.8" fill="${c}"/>`,

  // Abseilstand: Ring mit Pfeil nach unten
  rappel: (c) => `
    <circle cx="12" cy="7.4" r="5" fill="${INK}"/>
    <circle cx="12" cy="7.4" r="3.1" fill="${c}"/>
    <circle cx="12" cy="7.4" r="1.3" fill="${INK}"/>
    <path d="M12 12.4 V20 M8.4 16.6 L12 20.4 L15.6 16.6"
          fill="none" stroke="${INK}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M12 12.4 V20 M8.4 16.6 L12 20.4 L15.6 16.6"
          fill="none" stroke="${c}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>`,

  // Einstieg: Spitze nach oben über einer Standlinie
  start: (c) => `
    <path d="M12 3.4 L19.4 13.6 H4.6 Z" fill="${c}" stroke="${INK}" stroke-width="2.4" stroke-linejoin="round"/>
    <path d="M4.8 18.4 H19.2" stroke="${INK}" stroke-width="5" stroke-linecap="round"/>
    <path d="M4.8 18.4 H19.2" stroke="${c}" stroke-width="2.4" stroke-linecap="round"/>`,

  // Ausstieg / Gipfel
  top: (c) => `
    <path d="M6.6 21.2 V3.4" stroke="${INK}" stroke-width="5.6" stroke-linecap="round"/>
    <path d="M6.6 21.2 V3.4" stroke="${c}" stroke-width="2.4" stroke-linecap="round"/>
    <path d="M6.6 3.6 L18.6 7.6 L6.6 11.6 Z" fill="${c}" stroke="${INK}"
          stroke-width="2.4" stroke-linejoin="round"/>`,

  // Biwakplatz: Zelt mit dunklem Eingang, damit es nicht wie das Warndreieck aussieht
  bivouac: (c) => `
    <path d="M12 3.6 L20.8 19.8 H3.2 Z" fill="${c}" stroke="${INK}"
          stroke-width="2.4" stroke-linejoin="round"/>
    <path d="M12 9.8 L15.6 19.8 H8.4 Z" fill="${INK}"/>`,

  // Steinschlag / brüchiger Fels
  danger: (c) => `
    <path d="M12 3.6 L21.6 20 H2.4 Z" fill="${c}" stroke="${INK}" stroke-width="2.4" stroke-linejoin="round"/>
    <path d="M12 9 V14.4" stroke="${INK}" stroke-width="2.6" stroke-linecap="round"/>
    <circle cx="12" cy="17.4" r="1.5" fill="${INK}"/>`,
};

/** Reihenfolge und Beschriftung für die Legende. */
export const SYMBOL_LABELS = {
  belay: ['Standplatz', 'nummeriert, mit Grad und Länge der Seillänge'],
  bolt: ['Bohrhaken (BH)', 'geklebt oder gebohrt, verlässlich'],
  piton: ['Schlaghaken (NH)', 'vorgefundener Normalhaken, Zustand prüfen'],
  thread: ['Sanduhr (SU)', 'Fädelstelle, Bandschlinge nötig'],
  cam: ['Klemmkeil / Friend', 'mobile Sicherung empfohlen'],
  rappel: ['Abseilstand', 'Abseilpiste'],
  start: ['Einstieg', 'Beginn der Route am Wandfuß'],
  top: ['Ausstieg', 'Ende der Route am Grat'],
  bivouac: ['Biwakplatz', 'Sitz- oder Liegeplatz'],
  danger: ['Steinschlag / brüchig', 'erhöhte Vorsicht'],
};

/** Kurzform für die Seillängen-Tabelle. */
export const SYMBOL_SHORT = {
  bolt: 'BH', piton: 'NH', thread: 'SU', cam: 'mobil',
};

export function symbolSvg(type, color = '#ffffff', size = 26) {
  const glyph = (GLYPHS[type] || GLYPHS.bolt)(color);
  return `<svg class="sym" viewBox="0 0 24 24" width="${size}" height="${size}"`
       + ` aria-hidden="true" focusable="false">${glyph}</svg>`;
}

/** Linienmuster für die Legende (Kletterlinie, Gehgelände, Variante). */
export function lineSampleSvg(style, color = '#ffffff') {
  const dash = { solid: '', dashed: 'stroke-dasharray="9 7"', dotted: 'stroke-dasharray="1.5 7"' }[style] || '';
  return `<svg class="sym" viewBox="0 0 44 24" width="44" height="26" aria-hidden="true">
    <path d="M3 17 C 13 17, 13 7, 22 7 S 33 15, 41 6" fill="none" stroke="${INK}"
          stroke-width="7" stroke-linecap="round" ${dash}/>
    <path d="M3 17 C 13 17, 13 7, 22 7 S 33 15, 41 6" fill="none" stroke="${color}"
          stroke-width="3.2" stroke-linecap="round" ${dash}/>
  </svg>`;
}
