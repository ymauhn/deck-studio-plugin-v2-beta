// Deck Studio "Mover" mode, deck side (injected into /deck after picker.js). The studio page calls
// window.studioDrag.show(on, selection) and the box of that selection gets Moveable handles (ui/vendor, loaded on
// first use). A drag or a resize snaps to the 12-column grid the box sits in (its grid columns) and to the 8 px step
// (offsets and widths); on release the new layout goes to POST /api/drag/apply, and the slide then swaps or reloads.
// In this mode a click picks the grid column box under the pointer, a double click the innermost box there, and the
// deck sees no clicks (except in the overview, which a click leaves).
const STEP = 8;
const isTyping = (el) => el?.closest?.('input, textarea, select, [contenteditable]');
const studio = () => parent.studio;
const overview = () => document.getElementById('deck')?.classList.contains('ov');

const css = document.createElement('style');
css.textContent = '.moveable-control-box.studio-move { --moveable-color: #2a78d6; }'; // the picker's blue
document.head.append(css);

const snap = (v) => Math.round(v / STEP) * STEP;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const nearest = (list, v) => list.reduce((best, x, i) => (Math.abs(x - v) < Math.abs(list[best] - v) ? i : best), 0);
const px = (v) => (Math.round(v) ? `${Math.round(v)}px` : '0');

const shown = (el) => {
  for (let e = el; e; e = e.parentElement) {
    const cs = getComputedStyle(e);
    if (cs.visibility === 'hidden' || cs.opacity === '0') return false;
  }
  return true;
};
const visible = (el) => el?.isConnected && el.closest('section.slide.active') && shown(el) && !overview();

const grid12 = (el) => {
  const cs = el && getComputedStyle(el);
  return cs?.display === 'grid' && cs.gridTemplateColumns.split(' ').length === 12;
};

// left and right edges of each column of a grid, in slide units (the 1600 x 900 canvas)
function columns(grid, s, k) {
  const cs = getComputedStyle(grid);
  const gap = parseFloat(cs.columnGap) || 0;
  let x = (grid.getBoundingClientRect().left - s.left) / k + parseFloat(cs.borderLeftWidth) + parseFloat(cs.paddingLeft);
  const starts = [], ends = [];
  for (const w of cs.gridTemplateColumns.split(' ').map(parseFloat)) {
    starts.push(x);
    ends.push(x += w);
    x += gap;
  }
  return { starts, ends };
}

// the deck's own grid classes, from its style sheets: grid-column value -> class ('1 / 6' -> 'col-a')
let named;
function gridClasses() {
  if (named) return named;
  named = new Map();
  for (const sheet of document.styleSheets) {
    try {
      for (const r of sheet.cssRules) if (/^\.[\w-]+$/.test(r.selectorText) && r.style.gridColumn) named.set(r.style.gridColumn, r.selectorText.slice(1));
    } catch { /* a style sheet from another origin */ }
  }
  return named;
}

// why a box cannot move, or null
function refusal(el) {
  if (el.closest('.tbl')) return 'Tabela gerada a partir da dissertação: não se move aqui. Peça a mudança no chat.';
  if (el.closest('mjx-container, .eq')) return 'Fórmula gerada: não se move aqui. Peça a mudança no chat.';
  if (el.parentElement.closest('[data-component]')) return 'Parte de um componente: mova o componente inteiro.';
  if (el.parentElement.closest('svg') || (getComputedStyle(el).display === 'inline' && !el.matches('img, svg, video, canvas'))) {
    return 'Esta caixa fica dentro de um texto ou de um desenho: mova a caixa em volta dela.';
  }
  return null;
}

let on = false;
let item = null; // the Selection whose box has the handles
let box = null; // its element
let moveable; // a promise of the Moveable, made on first use
let start = null; // the box's layout when a drag or resize began, and the layout it would get now (start.next)
let dragged = false; // the click that ends a drag is not a pick

const elementOf = (sel) => document.querySelector(`#stage [data-loc="${CSS.escape(`${sel.loc.file}:${sel.loc.line}:${sel.loc.col}`)}"]`);

// the box of a Selection, or null (none, the slide itself or its grid, or a box that cannot move: tell says why)
function boxOf(sel, tell) {
  const el = sel && elementOf(sel);
  if (!el || el.matches('section.slide') || grid12(el)) return null;
  const why = refusal(el);
  if (why && tell) studio().ui.toast(why);
  return why ? null : el;
}

function handles() {
  moveable ??= import('/ui/vendor/moveable.min.js').then(() => new window.Moveable(document.body, {
    draggable: true, resizable: true, origin: false, className: 'studio-move',
  }).on('dragStart', begin).on('drag', drag).on('dragEnd', (e) => end(e, 'move'))
    .on('resizeStart', begin).on('resize', resize).on('resizeEnd', (e) => end(e, 'resize')));
  return moveable;
}

async function refresh() {
  if (on && box && !box.isConnected) box = boxOf(item, false); // a swap put in new copies of the slides
  if (!moveable && !(on && box)) return;
  const m = await handles();
  const target = on && visible(box) ? box : null;
  m.target = target; // always: Moveable's getter may still give the target before a pending one
  if (!target) return;
  m.renderDirections = grid12(target.parentElement) ? ['w', 'e'] : ['e']; // a box out of the grid grows to the right
  m.updateRect();
}

window.studioDrag = {
  show(value, sel, tell) {
    on = value;
    item = on ? sel : null;
    box = boxOf(item, tell);
    if (on) window.studioPicker?.clear(); // the handles mark the box now
    return refresh();
  },
};
document.addEventListener('deck:change', refresh);
addEventListener('transitionend', refresh, true); // fragments slide in
new ResizeObserver(refresh).observe(document.getElementById('deck') ?? document.body); // window size, notes pane

function begin(e) {
  const s = box.closest('section.slide').getBoundingClientRect();
  const k = s.width / 1600;
  const r = box.getBoundingClientRect();
  const t = getComputedStyle(box).translate;
  const [tx, ty] = t === 'none' ? [0, 0] : [...t.split(' ').map(parseFloat), 0];
  const grid = grid12(box.parentElement) ? columns(box.parentElement, s, k) : null;
  const left = (r.left - s.left) / k - tx;
  start = { x: e.clientX, y: e.clientY, k, tx, ty, left, w: r.width / k, style: box.getAttribute('style'), column: box.style.gridColumn, grid };
  if (grid) Object.assign(start, { a: nearest(grid.starts, left), b: nearest(grid.ends, left + start.w) });
}

// a drag: grid columns for a box in the grid, an offset in 8 px steps otherwise; up and down always an offset
function drag(e) {
  const { grid, a, b, k, tx, ty } = start;
  const dx = (e.clientX - start.x) / k, dy = (e.clientY - start.y) / k;
  if (!grid) return layout({ translate: [snap(tx + dx), snap(ty + dy)] });
  const to = clamp(nearest(grid.starts, start.left + dx), 0, grid.starts.length - 1 - (b - a));
  layout({ column: [to, to + b - a], translate: [tx, snap(ty + dy)] });
}

// a resize: the moved edge to a column edge for a box in the grid, the width in 8 px steps otherwise
function resize(e) {
  const { grid, a, b, k } = start;
  const dx = (e.clientX - start.x) / k;
  if (!grid) return layout({ width: Math.max(STEP, snap(start.w + dx)) });
  layout({ column: e.direction[0] > 0 ? [a, clamp(nearest(grid.ends, start.left + start.w + dx), a, grid.ends.length - 1)]
    : [clamp(nearest(grid.starts, start.left + dx), 0, b), b] });
}

// shows the layout on the box itself, over the source's own style
function layout(next) {
  start.next = next;
  box.setAttribute('style', start.style ?? '');
  if (next.column) box.style.gridColumn = `${next.column[0] + 1} / ${next.column[1] + 2}`;
  if (next.translate) box.style.translate = next.translate.map(px).join(' ');
  if (next.width) box.style.width = `${next.width}px`;
  moveable.then((m) => m.updateRect());
}

function revert() {
  if (start.style === null) box.removeAttribute('style');
  else box.setAttribute('style', start.style);
  moveable.then((m) => m.updateRect());
}

// the smallest change of the source that gives the box its new layout: a deck grid class where one fits and the box
// has no grid-column of its own, else style declarations
function change(next) {
  const style = {}, classes = { add: [], remove: [] };
  const [a, b] = next.column ?? [start.a, start.b];
  if (a !== start.a || b !== start.b) {
    const value = `${a + 1} / ${b + 2}`;
    const own = [...box.classList].filter((c) => [...gridClasses().values()].includes(c));
    const cls = !start.column && gridClasses().get(value);
    if (cls) classes.add.push(cls);
    else style['grid-column'] = value;
    classes.remove.push(...own.filter((c) => c !== cls));
  }
  const [x, y] = next.translate ?? [start.tx, start.ty];
  if (x !== start.tx || y !== start.ty) style.translate = x || y ? [x, y].map(px).join(' ') : null;
  if (next.width && next.width !== snap(start.w)) style.width = `${next.width}px`;
  return Object.keys(style).length || classes.add.length || classes.remove.length ? { style, classes } : null;
}

async function end(e, action) {
  const body = e.isDrag && start.next && change(start.next);
  dragged = e.isDrag;
  if (!body) return revert();
  const { status, data } = await studio().api('/api/drag/apply', { loc: item.loc, tag: box.localName, action, ...body });
  if (status === 200) return; // the swapped or reloaded slide brings the new layout from the source
  revert();
  studio().ui.toast(data?.message ?? `O studio não aceitou a mudança (erro ${status}).`, 'error');
}

// A click picks the box of the grid column under the pointer (the box itself outside a grid), as design tools pick a
// group first; a double click picks the innermost box there. Neither reaches the deck or the in-place text editor.
function pick(e, inner) {
  if (overview()) return;
  e.preventDefault();
  e.stopImmediatePropagation();
  if (dragged || e.target.closest('.moveable-control-box')) return;
  const s = document.querySelectorAll('#stage section.slide')[window.deck.state().slide - 1].getBoundingClientRect();
  const sel = window.studioPicker.selectionAt((e.clientX - s.left) / (s.width / 1600), (e.clientY - s.top) / (s.width / 1600));
  let el = sel && !inner && elementOf(sel);
  for (let p = el; p?.parentElement; p = p.parentElement) {
    if (grid12(p.parentElement) && p.dataset.loc) {
      el = p;
      break;
    }
  }
  if (sel) studio().selection.set([el ? window.studioPicker.selectionOf(el) : sel]);
}
addEventListener('pointerdown', () => { dragged = false; }, true);
addEventListener('click', (e) => on && pick(e, false), true);
addEventListener('dblclick', (e) => on && pick(e, true), true);

addEventListener('keydown', (e) => {
  if ((e.key !== 'm' && e.key !== 'M') || e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return;
  e.preventDefault();
  parent.postMessage({ type: 'studio:move' }, location.origin);
});
