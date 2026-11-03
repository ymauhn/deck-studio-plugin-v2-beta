// Deck Studio, deck side: a deck-swap event puts the edited slide files in place without a page reload
// (window.__studio.swap, from the kit's studio build). A file it cannot swap (slides added, removed or
// renamed) reloads the deck instead, on the same slide and step; /deck waits for the full build.
function listen() {
  const studio = parent.studio;
  const off = studio?.on('deck-swap', ({ parts }) => {
    if (!parts.every((p) => window.__studio?.swap(p.slides, p.css))) return studio.deck.reload();
    // the picked boxes went with the old slides: drop the marks, then re-anchor each chip to the new nodes (by text),
    // so an edit above a box does not leave its chip (or the next message) pointing at the old line
    window.studioPicker?.clear();
    const p = window.studioPicker;
    studio.selection.set(studio.selection.get().map((s) => (p?.resolve ? p.resolve(s) : s)).filter(Boolean));
  });
  addEventListener('pagehide', () => off?.());
}

// the deck may load before the studio page's app.js, which makes window.studio before its DOMContentLoaded
if (parent.studio) listen();
else if (parent !== window) parent.addEventListener('DOMContentLoaded', listen, { once: true });
