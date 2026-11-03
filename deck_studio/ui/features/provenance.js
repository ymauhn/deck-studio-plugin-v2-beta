// "Origem": while on, hovering a number on a slide shows where it comes from (ui/deck/provenance.js draws the chip).
// Only a deck whose numbers have sources to trace (project.provenance: the NEXUS-GO dissertation) gets the button.
export default function provenance(studio) {
  if (!studio.project?.provenance) return;
  let on = false;
  const sync = () => studio.deck.win()?.studioProvenance?.setMode(on);
  const button = studio.ui.addToolbarButton({
    id: 'provenance', label: 'Origem', title: 'Mostrar de onde vem cada número ao passar o mouse', pressed: false,
    onClick() {
      on = !on;
      button.setAttribute('aria-pressed', String(on));
      sync();
    },
  });
  studio.deck.frame.addEventListener('load', sync); // a reloaded deck starts off
  studio.on('deck-swap', sync); // swapped slides may carry other numbers: the deck side fetches the index again
}
