// Deck Studio number provenance, deck side (injected into /deck after picker.js): while the studio's "Origem"
// toggle is on, the number under the pointer gets a chip with its source, from GET /api/provenance. The number is
// read where it is (caretPositionFromPoint); the deck DOM stays as built, the chip lives outside the stage.
// The studio page turns it on and off with window.studioProvenance.setMode(on).
const NUMBER = /(?<![\p{L}\p{N}_.])\d+(?:,\d{3})*(?:\.\d+)?(?![\p{L}\p{N}_])/gu; // the audit's numbers (provenance.py)

const css = document.createElement('style');
css.textContent = `
#studio-provenance {
  position: fixed; z-index: 2147483647; pointer-events: none; max-width: 420px; box-sizing: border-box;
  display: flex; flex-direction: column; gap: 2px; padding: 6px 10px; border-radius: 8px;
  font: 400 12px/1.4 var(--font-body, system-ui, sans-serif); color: #0f1d29;
  background: #e7f6ef; border: 1px solid #1baf7a; box-shadow: 0 4px 16px rgb(15 29 41 / 18%);
}
#studio-provenance[hidden] { display: none; }
#studio-provenance b, #studio-provenance .tex { font-family: var(--font-data, ui-monospace, monospace); }
#studio-provenance b { font-weight: 600; color: #127552; }
#studio-provenance.loose { background: #fbfcfd; border-style: dashed; }
#studio-provenance.loose b { color: #43525f; }
#studio-provenance.reason { background: #fbfcfd; border-color: #d9e0e6; }
#studio-provenance.reason b { color: #43525f; }
#studio-provenance.missing { background: #fcede5; border-color: #c2410c; }
#studio-provenance.missing b { color: #c2410c; }`;
document.head.append(css);
const chip = Object.assign(document.createElement('div'), { id: 'studio-provenance', hidden: true });
chip.setAttribute('role', 'tooltip');
document.body.append(chip);

let on = false;
let index = { slides: {} };

const line = (tag, text, className = '') => Object.assign(document.createElement(tag), { className, textContent: text });
const inside = (r, x, y) => x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;

// the number under (x, y) on a slide, with its index entry and its box, or null. Only authored text that shows
// counts: the studio build gives every authored element of a slide a data-loc, so text the build or the engine
// drew (tables, components, the header) has none.
function numberAt(x, y) {
  const node = document.caretPositionFromPoint(x, y)?.offsetNode;
  const el = node?.nodeType === Node.TEXT_NODE ? node.parentElement : null;
  if (!el?.hasAttribute('data-loc') || !el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return null;
  const section = el.closest('section.slide');
  if (!section) return null;
  for (const m of node.data.matchAll(NUMBER)) {
    const range = document.createRange();
    range.setStart(node, m.index);
    range.setEnd(node, m.index + m[0].length);
    if ([...range.getClientRects()].some((r) => inside(r, x, y))) {
      return { entry: index.slides[section.id]?.find((e) => e.number === m[0]), box: range.getBoundingClientRect() };
    }
  }
  return null;
}

// [class, lines]: the first .tex line with its snippet (and where else), else the audit's reason, else "sem origem".
// A loose line holds the number only inside another term or in a comment: a weaker chip.
function content({ sources: [first, ...more], reason }) {
  if (first) {
    return [first.loose ? 'loose' : '', [line('b', `${first.file.split('/').pop()}:L${first.line}`), line('span', first.snippet, 'tex'),
      ...(more.length ? [line('span', `também ${more.map((s) => `L${s.line}`).join(', ')}`)] : []),
      ...(first.loose ? [line('span', 'Só aparece dentro de outro termo ou num comentário.')] : [])]];
  }
  if (reason) return ['reason', [line('b', 'number_audit.md'), line('span', reason)]];
  return ['missing', [line('b', 'sem origem'), line('span', 'Não está na dissertação nem na auditoria de números.')]];
}

function show({ entry, box }) {
  const [kind, lines] = content(entry);
  chip.className = kind;
  chip.replaceChildren(...lines);
  chip.hidden = false;
  // under the number, or over it when there is no room below; always inside the deck
  const below = box.bottom + 6;
  const top = below + chip.offsetHeight <= innerHeight - 4 ? below : Math.max(4, box.top - 6 - chip.offsetHeight);
  const left = Math.max(4, Math.min(box.left, innerWidth - 4 - chip.offsetWidth));
  Object.assign(chip.style, { left: `${left}px`, top: `${top}px` });
}

let pointer = null; // the last pointer position on the deck
function update() {
  const hit = on && pointer && numberAt(pointer.x, pointer.y);
  if (hit?.entry) show(hit);
  else chip.hidden = true;
}
addEventListener('pointermove', (e) => {
  pointer = { x: e.clientX, y: e.clientY };
  update();
});
document.documentElement.addEventListener('mouseleave', () => {
  pointer = null;
  update();
});
document.addEventListener('deck:change', update); // another step or slide under a resting pointer

async function setMode(value) {
  on = value;
  update();
  if (!on) return;
  const { status, data } = await parent.studio.api('/api/provenance');
  if (status === 200) index = data;
  else parent.studio.ui.toast(data?.message ?? `A origem dos números não carregou (erro ${status}).`, 'error');
  update(); // the pointer may already rest on a number
}

window.studioProvenance = { setMode };
