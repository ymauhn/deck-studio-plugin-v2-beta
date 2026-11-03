// Deck Studio in-place text editing, injected into the studio deck (/deck) after picker.js.
// Outside select mode, a double click on a plain text box edits that one text node where it is:
// Enter saves it to the source (POST /api/edit-text), Esc cancels. Math, tables and components are
// generated, so a double click there only says why they cannot be edited here.
const INTERACTIVE = 'button, input, select, textarea, a, label, [data-interactive]'; // the deck engine's own list
const GENERATED = '[data-component], .tbl, mjx-container, .eq';
const DOUBLE_CLICK_MS = 500; // the Windows default: until then a click on text may still become a double click

const css = document.createElement('style');
css.textContent = `
.studio-editing { outline: 2px solid #2a78d6; outline-offset: 3px; border-radius: 2px; cursor: text; }
.studio-editing[contenteditable="false"] { opacity: .6; }`;
document.head.append(css);

const studio = () => parent.studio; // the studio page (same origin), read late: it may load after the deck

const shown = (el) => {
  for (let e = el; e; e = e.parentElement) {
    const cs = getComputedStyle(e);
    if (cs.visibility === 'hidden' || cs.opacity === '0') return false;
  }
  return true;
};

// What a double click at this event's point works on: a plain text node of an authored box, 'generated', or null.
function target(e) {
  const t = e.target;
  if (!studio() || !t.closest?.('section.slide') || t.closest(`${INTERACTIVE}, #deck.ov`) || !shown(t)) return null;
  if (t.closest(GENERATED)) return 'generated';
  const node = document.caretPositionFromPoint(e.clientX, e.clientY)?.offsetNode;
  const box = node?.nodeType === Node.TEXT_NODE && node.data.trim() && node.parentElement;
  return box?.matches('[data-loc]') && !box.closest(GENERATED) ? node : null;
}

// The deck takes a click as the next or previous step. A click on text first waits out the double-click time,
// so the clicks of a double click never move the deck; a lone click is then replayed to the deck.
let held;
let replaying = false;
addEventListener('click', (e) => {
  if (replaying || !target(e)) return;
  e.stopImmediatePropagation();
  clearTimeout(held);
  if (e.detail > 1) return;
  const { target: el, clientX, clientY, screenX, screenY } = e;
  held = setTimeout(() => {
    replaying = true;
    el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window, detail: 1, clientX, clientY, screenX, screenY }));
    replaying = false;
  }, DOUBLE_CLICK_MS);
}, true);

let open = null; // the editor in use: { cancel }

addEventListener('dblclick', (e) => {
  const t = target(e);
  if (!t) return;
  open?.cancel();
  if (t === 'generated') studio().ui.toast('Conteúdo gerado (fórmula, tabela ou componente) não se edita aqui. Peça a mudança no chat.');
  else edit(t);
}, true);

function edit(node) {
  const box = node.parentElement;
  const [, file, line, col] = /^(.*):(\d+):(\d+)$/.exec(box.dataset.loc);
  const childIndex = [...box.childNodes].indexOf(node);
  const old = node.data;
  const sel = getSelection(); // the word the double click selected stays selected in the editor
  const r = sel.rangeCount ? sel.getRangeAt(0) : null;
  const [from, to] = r?.startContainer === node && r.endContainer === node ? [r.startOffset, r.endOffset] : [0, 0];
  const span = Object.assign(document.createElement('span'), { className: 'studio-editing', contentEditable: 'plaintext-only' });
  span.dataset.interactive = ''; // the deck leaves clicks inside it alone
  span.setAttribute('role', 'textbox');
  span.setAttribute('aria-label', 'Editar texto');
  node.before(span);
  span.append(node);
  span.focus({ preventScroll: true });
  sel.setBaseAndExtent(node, from, node, to);

  const close = (text) => span.replaceWith(text);
  open = { cancel: () => { open = null; close(old); } };

  async function save() {
    open = null;
    // contenteditable types a no-break space where a plain one would collapse; the kit's sources have none
    const text = span.textContent.replaceAll('\u00a0', ' ');
    if (text.trim() === old.trim()) return close(old);
    span.contentEditable = 'false';
    const { status, data } = await studio().api('/api/edit-text', {
      loc: { file, line: +line, col: +col }, childIndex, oldText: old, newText: text });
    if (status === 200) return close(text);
    if (status === 409 && data?.error === 'busy') { // a turn holds the lock: keep the typing, let the author retry
      span.contentEditable = 'plaintext-only';
      open = { cancel: () => { open = null; close(old); } };
      span.focus({ preventScroll: true });
      studio().ui.toast(data.message, 'error');
      return;
    }
    close(old);
    studio().ui.toast(data?.message ?? `O studio não aceitou a edição (erro ${status}).`, 'error');
  }

  span.addEventListener('keydown', (e) => {
    e.stopPropagation(); // arrows, space and letters edit the text, not the deck
    if (e.key === 'Escape' && open) open.cancel();
    if (e.key === 'Enter' && !e.isComposing && open) {
      e.preventDefault();
      save();
    }
  });
}
