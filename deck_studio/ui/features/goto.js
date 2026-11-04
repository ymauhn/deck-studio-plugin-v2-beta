// "Ir para o slide" (feedback of 2026-11-04): a field in the top bar that takes the deck to slide N, or to a backup
// slide as B9, and shows how many slides the deck has. It reads the deck's own labels, so it works the same with the
// English and the Portuguese deck, and after every reload.
export default function goto(studio) {
  const form = Object.assign(document.createElement('form'), { className: 'goto' });
  form.setAttribute('role', 'search');
  const label = Object.assign(document.createElement('label'), { htmlFor: 'goto-n', textContent: 'Ir para o slide' });
  const input = Object.assign(document.createElement('input'), {
    id: 'goto-n', type: 'text', inputMode: 'text', autocomplete: 'off', placeholder: 'N ou B1', size: 5,
  });
  input.setAttribute('aria-describedby', 'goto-total');
  const total = Object.assign(document.createElement('span'), { id: 'goto-total', className: 'goto-total' });
  form.append(label, input, total);
  document.querySelector('header.top .usage').before(form);

  const engine = () => {
    const d = studio.deck.win()?.deck;
    return typeof d?.labels === 'function' ? d : null;
  };

  function count() {
    const d = engine();
    if (!d) return;
    const s = d.state();
    total.textContent = `de ${s.total}` + (s.backups ? ` + ${s.backups} de reserva` : '');
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const d = engine();
    const want = input.value.trim().toUpperCase().replace(/^S(?=\d)/, '');
    if (!d || !want) return;
    // the deck's labels: "1".."N" for the talk, "B1".."Bn" for the backup slides
    const index = d.labels().findIndex((l) => l.toUpperCase() === want || l.toUpperCase() === want.replace(/^0+(?=\d)/, ''));
    if (index < 0) {
      studio.ui.toast(`O deck não tem o slide ${input.value.trim()}.`, 'error');
      return;
    }
    d.go(index + 1, 0);
    input.value = '';
    studio.deck.win().focus(); // the arrows move the deck again
  });

  // the count follows the deck: its first start, every reload, the other language
  studio.deck.frame.addEventListener('load', () => {
    const ready = () => (engine() ? count() : setTimeout(ready, 50));
    ready();
  });
  studio.on('deck-swap', () => setTimeout(count, 150));
  count();
}
