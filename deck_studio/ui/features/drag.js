// "Mover (M)": handles on the selected box, to drag and resize it on the deck's 12-column grid (ui/deck/drag.js).
// On release the new layout goes to the source as one undoable edit, and its card comes like any other edit's.
// In this mode a click picks a box without moving the deck; select mode and this mode take turns with the pointer.
const isTyping = (el) => el?.closest?.('input, textarea, select, [contenteditable]');

export default function drag(studio) {
  const pick = document.getElementById('pick');
  let on = false;
  const button = studio.ui.addToolbarButton({
    id: 'move', label: 'Mover (M)', title: 'Mover e redimensionar a caixa selecionada no grid', pressed: false,
    onClick: () => set(!on),
  });
  button.setAttribute('aria-keyshortcuts', 'M');
  // tell: say why a box cannot move; a reloaded deck gets the mode back without a word
  const show = (tell) => studio.deck.win()?.studioDrag?.show(on, studio.selection.get()[0] ?? null, tell);

  function set(value) {
    on = value;
    button.setAttribute('aria-pressed', String(on));
    if (on && pick.getAttribute('aria-pressed') === 'true') pick.click(); // the picker would take every click
    show(true);
  }

  new MutationObserver(() => on && pick.getAttribute('aria-pressed') === 'true' && set(false))
    .observe(pick, { attributeFilter: ['aria-pressed'] });
  studio.selection.subscribe(() => on && show(true));
  studio.deck.frame.addEventListener('load', () => show(false));
  document.addEventListener('keydown', (e) => {
    if ((e.key !== 'm' && e.key !== 'M') || e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return;
    e.preventDefault();
    set(!on);
  });
  addEventListener('message', (e) => {
    if (e.origin === location.origin && e.source === studio.deck.win() && e.data?.type === 'studio:move') set(!on);
  });
}
