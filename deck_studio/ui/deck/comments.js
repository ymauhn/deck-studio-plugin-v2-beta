// Deck Studio comments, deck side (injected into /deck after picker.js): numbered pins on the commented boxes of the
// slide on screen, in an overlay outside the deck (its DOM stays as built), and the C key.
// The studio page hands over the comments with window.studioComments.show(list); a comment's number is its place + 1.
const isTyping = (el) => el?.closest?.('input, textarea, select, [contenteditable]');
const PIN = 22;

const css = document.createElement('style');
css.textContent = `
#studio-comments { position: fixed; inset: 0; z-index: 2147483646; pointer-events: none; overflow: hidden; }
.studio-pin {
  position: absolute; width: ${PIN}px; height: ${PIN}px; box-sizing: border-box; border-radius: 50%;
  display: grid; place-items: center; font: 700 12px/1 system-ui, sans-serif;
  background: #eb6834; color: #fff; border: 2px solid #fff; box-shadow: 0 1px 4px rgb(15 29 41 / 35%);
}
.studio-pin.sent { background: #fdf0e8; color: #b4441a; border-color: #eb6834; }`;
document.head.append(css);
const layer = Object.assign(document.createElement('div'), { id: 'studio-comments' });
layer.setAttribute('aria-hidden', 'true'); // the studio's comments panel lists them
document.body.append(layer);

let comments = [];

function draw() {
  const section = document.querySelector('#stage section.slide.active');
  const boxes = section ? [section, ...section.querySelectorAll('[data-loc]')] : [];
  const onBox = new Map(); // element -> pins drawn on it so far
  const pins = [];
  const norm = (el) => el.textContent.replace(/\s+/g, ' ').trim().slice(0, 2000);
  comments.forEach((c, i) => {
    for (const { loc, tag, text } of c.selection) {
      // find the box again by its text first (an edit above it moves its line, not its words), then by the stored
      // loc; no match means its text changed or it is gone, so no pin, instead of landing on the neighbour
      const el = (text && boxes.find((b) => b.localName === tag && norm(b) === text))
        || (loc && boxes.find((b) => b.dataset.loc === `${loc.file}:${loc.line}:${loc.col}` && b.localName === tag));
      const r = el?.getBoundingClientRect();
      if (!r || (!r.width && !r.height)) continue;
      const n = onBox.get(el) ?? 0;
      onBox.set(el, n + 1);
      const pin = Object.assign(document.createElement('b'), { className: `studio-pin${c.sent ? ' sent' : ''}`, textContent: i + 1 });
      // on the box's top right corner; more pins on one box line up to the left
      const left = Math.max(0, Math.min(innerWidth - PIN, r.right - PIN / 2 - n * (PIN + 4)));
      Object.assign(pin.style, { left: `${left}px`, top: `${Math.max(0, r.top - PIN / 2)}px` });
      pins.push(pin);
    }
  });
  layer.replaceChildren(...pins);
}

window.studioComments = {
  show(list) {
    comments = list;
    draw();
  },
};
document.addEventListener('deck:change', draw);
addEventListener('transitionend', draw, true); // fragments slide in
addEventListener('scroll', draw, true); // the overview scrolls
new ResizeObserver(draw).observe(document.getElementById('deck') ?? document.body); // window size, notes pane

addEventListener('keydown', (e) => {
  if ((e.key !== 'c' && e.key !== 'C') || e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return;
  e.preventDefault();
  parent.postMessage({ type: 'studio:comment' }, location.origin);
});
