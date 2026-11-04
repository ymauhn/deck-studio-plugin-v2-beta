// "Seguir o agente" (feedback of 2026-11-04): while the agent edits, the deck goes by itself to the slide of each
// write, shown at its last step, and the changed box flashes for a moment. On by default; the button turns it off
// and on, and that choice stays. When the author moves the deck by hand during a request, following pauses until the
// next request.
// The server sends `agent-edit` {file, line} before it rebuilds; the deck is moved once the edit is on screen (after
// the deck-swap, or after the reload of the deck page).
const FLASH_MS = 1600;
const FLASH_CSS = `.studio-flash { outline: 4px solid #f59e0b !important; outline-offset: 6px; border-radius: 4px;
  transition: outline-color 600ms ease; }
.studio-flash.studio-flash-out { outline-color: transparent !important; }`;

export default function follow(studio) {
  const bar = document.querySelector('.deck-bar');
  const button = Object.assign(document.createElement('button'), {
    type: 'button', className: 'btn', textContent: 'Seguir o agente',
    title: 'Mostra o slide que o agente está editando. Navegar à mão desliga até o próximo pedido.',
  });
  bar.append(button);

  let on = true; // the author's choice, with the button
  let paused = false; // the author moved the deck by hand during this request
  let busy = false;
  let pending = null; // the last agent-edit not shown yet
  let moving = false; // our own deck.go, which is not the author navigating

  const following = () => on && !paused;
  const show = () => button.setAttribute('aria-pressed', String(following()));
  show();
  button.addEventListener('click', () => {
    if (following()) on = false;
    else { on = true; paused = false; }
    show();
  });

  // a new request ends the pause (not the author's off)
  studio.on('chat', (e) => {
    if (e.kind === 'user' && !e.replay) { paused = false; show(); }
  });
  studio.on('status', (s) => { busy = !!s.busy; });
  studio.on('agent-edit', (e) => { pending = e; });
  studio.on('deck-swap', () => setTimeout(apply, 120)); // swap.js puts the new slides in first

  function target(doc, { file, line }) {
    // the element whose start tag is the last one at or before the changed line, in that file
    let best = null;
    let bestLine = -1;
    for (const el of doc.querySelectorAll(`[data-loc^="${CSS.escape(file)}:"]`)) {
      const at = +el.dataset.loc.slice(file.length + 1).split(':')[0];
      if (at <= line && at >= bestLine) { best = el; bestLine = at; }
    }
    return best;
  }

  function apply() {
    if (!pending || !following()) return;
    const win = studio.deck.win();
    const doc = win?.document;
    const engine = win?.deck;
    if (!doc || typeof engine?.steps !== 'function') return;
    const el = target(doc, pending);
    pending = null;
    const section = el?.closest('section.slide');
    if (!section) return;
    const index = [...doc.querySelectorAll('section.slide')].indexOf(section) + 1;
    moving = true;
    try { engine.go(index, engine.steps()[index - 1]); } finally { moving = false; }
    if (!doc.getElementById('studio-flash-css')) {
      doc.head.append(Object.assign(doc.createElement('style'), { id: 'studio-flash-css', textContent: FLASH_CSS }));
    }
    const box = el === section ? section : el;
    box.classList.remove('studio-flash', 'studio-flash-out');
    box.classList.add('studio-flash');
    setTimeout(() => box.classList.add('studio-flash-out'), FLASH_MS - 600);
    setTimeout(() => box.classList.remove('studio-flash', 'studio-flash-out'), FLASH_MS);
  }

  // the author moving the deck during a request stops following. Only the author's own input counts (a trusted key or
  // click in the deck), not a deck.go of the studio, such as the one that keeps the place across a reload. Capture
  // phase: the engine handles the keys before they bubble; the picker, registered first, swallows its clicks
  const NAV = /^(Arrow(Left|Right|Up|Down)|PageUp|PageDown|Home|End| |Enter|Backspace|\d)$/;
  const manual = () => {
    if (!moving && busy && following()) { paused = true; show(); }
  };
  function watch() {
    const win = studio.deck.win();
    win?.addEventListener('keydown', (e) => e.isTrusted && NAV.test(e.key) && manual(), true);
    win?.addEventListener('click', (e) => e.isTrusted && manual(), true);
  }
  studio.deck.frame.addEventListener('load', () => {
    watch();
    // a reloaded deck: wait for its engine, then show the pending edit
    const ready = () => (typeof studio.deck.win()?.deck?.steps === 'function' ? apply() : setTimeout(ready, 50));
    ready();
  });
  watch();
}
