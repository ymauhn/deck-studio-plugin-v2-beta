// Deck bar hint and step readout (the approved wireframe "A tela"): a line telling the author that a double click
// edits text in place, and a "passo N de M" that follows the deck. Both live in the deck bar, so Beamer mode hides
// them with the rest of the HTML deck's tools (beamer.css hides .deck-bar children that are not the Beamer bar).
export default function deckhint(studio) {
  const bar = document.querySelector('.deck-bar');
  const hint = Object.assign(document.createElement('span'), {
    className: 'deck-hint', textContent: 'Duplo clique num texto: edita ali mesmo' });
  const step = Object.assign(document.createElement('span'), { className: 'deck-step' });
  step.setAttribute('role', 'status');
  step.setAttribute('aria-label', 'Passo atual');
  bar.append(hint, step);

  function update() {
    const s = studio.deck.state();
    if (!s) return; // the deck has not started yet
    step.textContent = `passo ${s.fragment + 1} de ${s.fragmentsOnSlide + 1}`;
  }
  // deck:change fires inside the iframe; re-attach after each (re)load, as the Files pane does
  const watch = () => studio.deck.win().document.addEventListener('deck:change', update);
  studio.deck.frame.addEventListener('load', () => { watch(); update(); });
  watch();
  update();
}
