// Autonomy switch, above the message box: how much the agent does without asking. It is one studio setting
// (POST /api/settings {autonomy}) and applies from the agent's next tool call on, in every chat. At every level the
// write guard keeps blocking writes outside the deck, and publishing or any other external action still asks.
const LEVELS = [
  { value: 'ask', label: 'Perguntar sempre', hint: 'Toda escrita, comando e acesso à web espera o seu Permitir.' },
  { value: 'deck', label: 'Editar o deck', hint: 'Edita os arquivos do deck sem perguntar; comandos, web e scripts do deck pedem aprovação.' },
  { value: 'auto', label: 'Autônomo', hint: 'Também roda comandos locais, lê e consulta a web sem perguntar. Publicar, rede, scripts do deck e o que fica fora do deck ainda pedem aprovação.' },
];

export default async function autonomy(studio) {
  const group = Object.assign(document.createElement('div'), { className: 'autonomy' });
  group.setAttribute('role', 'radiogroup');
  group.setAttribute('aria-label', 'Autonomia do agente');
  const title = Object.assign(document.createElement('span'), { className: 'autonomy-label', textContent: 'Autonomia' });
  group.append(title);
  const buttons = LEVELS.map((l) => {
    const b = Object.assign(document.createElement('button'), { type: 'button', textContent: l.label, title: l.hint });
    b.setAttribute('role', 'radio');
    b.dataset.level = l.value;
    b.addEventListener('click', () => choose(l.value));
    group.append(b);
    return b;
  });
  document.querySelector('#composer').prepend(group);

  function show(level) {
    for (const b of buttons) {
      const on = b.dataset.level === level;
      b.setAttribute('aria-checked', String(on));
      b.tabIndex = on ? 0 : -1;
    }
  }

  async function choose(level) {
    const before = buttons.find((b) => b.getAttribute('aria-checked') === 'true')?.dataset.level;
    show(level);
    const { status, data } = await studio.api('/api/settings', { autonomy: level });
    if (status !== 200) {
      show(before);
      studio.ui.toast(data?.message ?? `O studio não mudou a autonomia (erro ${status}).`, 'error');
    }
  }

  // arrows move between the levels, as in any radio group
  group.addEventListener('keydown', (e) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (!step) return;
    e.preventDefault();
    const i = buttons.findIndex((b) => b.getAttribute('aria-checked') === 'true');
    const next = buttons[(i + step + buttons.length) % buttons.length];
    next.focus();
    choose(next.dataset.level);
  });

  const { data } = await studio.api('/api/settings');
  show(data?.autonomy ?? 'deck');
}
