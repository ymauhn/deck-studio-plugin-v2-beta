// Deck Studio picker, injected by the server into the studio deck (/deck) only.
// The studio page calls window.studioPicker directly (same origin, synchronous: a click right after
// a mode change cannot overtake it); the picker answers with postMessage to its own origin only.
const ORIGIN = location.origin;
const post = (msg) => parent.postMessage(msg, ORIGIN);
const isTyping = (el) => el?.closest?.('input, textarea, select, [contenteditable]');
let on = false;
let paused = false; // the deck is rebuilding: its boxes may no longer be in the sources

const css = document.createElement('style');
css.textContent = `
.studio-box { position: fixed; z-index: 2147483647; pointer-events: none; display: none; border-radius: 2px; }
#studio-hover { outline: 2px dashed #2a78d6; outline-offset: 2px; }
.studio-selected { outline: 2px solid #2a78d6; outline-offset: 2px; background: rgba(42, 120, 214, .08); }
.studio-picking, .studio-picking * { cursor: crosshair !important; user-select: none !important; }
.studio-picking.studio-paused, .studio-picking.studio-paused * { cursor: progress !important; }`;
document.head.append(css);
const hover = Object.assign(document.createElement('div'), { id: 'studio-hover', className: 'studio-box' });
document.body.append(hover);

function place(box, el) {
  const r = el?.getBoundingClientRect();
  box.style.display = r ? 'block' : 'none';
  if (r) Object.assign(box.style, { left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px` });
}

const shown = (el) => {
  for (let e = el; e; e = e.parentElement) {
    const cs = getComputedStyle(e);
    if (cs.visibility === 'hidden' || cs.opacity === '0') return false;
  }
  return true;
};

// The box at (x, y): the topmost visible element of a slide, mapped to its component container
// (runtime DOM is not source) or else to the nearest element with a source location.
function boxAt(x, y) {
  const hit = document.elementsFromPoint(x, y).find((el) => el.closest('section.slide') && shown(el));
  return hit && (hit.closest('[data-component]') ?? hit.closest('[data-loc]'));
}

function setMode(value, tell = true) {
  on = value;
  document.documentElement.classList.toggle('studio-picking', on);
  if (!on) place(hover, null);
  if (tell) post({ type: 'studio:mode', on });
}

// while the deck rebuilds, select mode still keeps the pointer from the deck but picks nothing
function pause(value) {
  paused = value;
  document.documentElement.classList.toggle('studio-paused', paused);
  if (paused) place(hover, null);
}

addEventListener('pointermove', (e) => { if (on && !paused) place(hover, boxAt(e.clientX, e.clientY)); }, true);
document.documentElement.addEventListener('mouseleave', () => place(hover, null));

// ---------- selection ----------
let selected = []; // [{ el, info }]: info is the Selection taken when the box was picked
const marks = [];

const kindOf = (el) => (el.matches('[data-component]') ? 'component'
  : el.matches('.tbl') ? 'table' // built from the dissertation's tables
  : el.matches('mjx-container, .eq') ? 'math'
  : el.matches('figure, img, svg, picture, video') ? 'figure'
  : [...el.childNodes].some((n) => n.nodeType === Node.TEXT_NODE && n.data.trim()) ? 'text'
  : 'element');

const ENGINE_CLASSES = ['on', 'off', 'active']; // fragment and slide state added at runtime, not in the source

// SPEC "Selection", taken when the box is picked; rect is in slide units (the 1600 x 900 canvas)
function describe(el) {
  const [, file, line, col] = /^(.*):(\d+):(\d+)$/.exec(el.dataset.loc);
  const section = el.closest('section.slide');
  const slide = [...document.querySelectorAll('#stage section.slide')].indexOf(section) + 1;
  const state = window.deck.state();
  const s = section.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  const k = s.width / 1600;
  const kind = kindOf(el);
  return {
    slideId: section.id, slide, step: slide === state.slide ? state.fragment : window.deck.steps()[slide - 1], // overview shows every step
    part: file.split('/').pop(), loc: { file, line: +line, col: +col },
    tag: el.localName, classes: [...el.classList].filter((c) => !ENGINE_CLASSES.includes(c)),
    text: el.textContent.replace(/\s+/g, ' ').trim().slice(0, 2000), outerHTML: el.outerHTML.slice(0, 2000),
    kind, ...(kind === 'component' && { component: el.dataset.component }),
    rect: { x: Math.round((r.left - s.left) / k), y: Math.round((r.top - s.top) / k), w: Math.round(r.width / k), h: Math.round(r.height / k) },
  };
}

function drawSelection() {
  for (const m of marks.splice(0)) m.remove();
  for (const { el } of selected) {
    const m = Object.assign(document.createElement('div'), { className: 'studio-box studio-selected' });
    document.body.append(m);
    place(m, el.closest('section.slide.active') && el);
    marks.push(m);
  }
}

// a plain click replaces the selection, Shift+click adds the box (or takes it out again)
function select(el, add) {
  const picked = { el, info: describe(el) };
  selected = !add ? [picked] : selected.some((s) => s.el === el) ? selected.filter((s) => s.el !== el) : [...selected, picked];
  drawSelection();
  post({ type: 'studio:selection', selection: selected.map((s) => s.info) });
}

function clear(tell = true) {
  selected = [];
  drawSelection();
  if (tell) post({ type: 'studio:selection', selection: [] });
}

// in select mode the deck never sees the pointer: no slide change, no component reaction
const swallow = (e) => { if (on) e.stopImmediatePropagation(); };
for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'dblclick', 'auxclick']) addEventListener(type, swallow, true);
addEventListener('click', (e) => {
  if (!on) return;
  e.preventDefault();
  e.stopImmediatePropagation();
  const el = !paused && boxAt(e.clientX, e.clientY);
  if (el) select(el, e.shiftKey);
}, true);
document.addEventListener('deck:change', drawSelection);
addEventListener('resize', drawSelection);

// The Selection of the topmost visible box at (x, y) in slide units (the 1600 x 900 canvas) on the current
// slide and step, or null: for selections that start elsewhere (a Beamer page, a comment pin)
function selectionAt(x, y) {
  if (!(x >= 0 && x <= 1600 && y >= 0 && y <= 900)) return null;
  const section = document.querySelectorAll('#stage section.slide')[window.deck.state().slide - 1];
  const s = section.getBoundingClientRect();
  const k = s.width / 1600;
  const el = boxAt(s.left + x * k, s.top + y * k);
  return el?.closest('section.slide') === section ? describe(el) : null;
}

// Re-anchor a Selection to its box in the current DOM, after a swap or reload: find the box by its text (so an
// edit that shifted its line still matches), then by its stored loc; null when it is gone or its text changed.
function resolve(sel) {
  if (!sel?.slideId || !sel.loc) return sel?.kind === 'tex' ? sel : null;
  const section = document.getElementById(sel.slideId);
  if (!section) return null;
  const boxes = [section, ...section.querySelectorAll('[data-loc]')];
  const el = (sel.text && boxes.find((b) => b.localName === sel.tag
      && b.textContent.replace(/\s+/g, ' ').trim().slice(0, 2000) === sel.text))
    || boxes.find((b) => b.dataset.loc === `${sel.loc.file}:${sel.loc.line}:${sel.loc.col}` && b.localName === sel.tag);
  return el ? describe(el) : null;
}

// selectionOf(el): the Selection of a box element (one with data-loc), as a click on it would take it
window.studioPicker = { setMode: (value) => setMode(value, false), clear: () => clear(false), pause, selectionAt, selectionOf: describe, resolve };

addEventListener('keydown', (e) => {
  if (e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return;
  if (e.key === 's' || e.key === 'S') {
    e.preventDefault();
    setMode(!on);
  }
  if (e.key === 'Escape' && selected.length) clear();
}, true);
