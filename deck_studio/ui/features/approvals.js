// Approval cards: the agent waits while the author permits or denies a tool call the guard asks about.
// An `approval` event with state "pending" shows the card; the next one for the same id closes it.
// Cards still open when the page loads come from GET /api/approvals.
const ENDED = {
  allow: 'Permitido', deny: 'Negado', timeout: 'Negado: sem resposta a tempo.', cancelled: 'Cancelado: o pedido parou.',
};

export default function (studio) {
  const cards = new Map(); // approval id -> card

  function card(e) {
    const el = Object.assign(document.createElement('article'), { className: 'approval' });
    el.setAttribute('aria-label', `Aprovação: ${e.tool}`);
    const what = Object.assign(document.createElement('p'), { className: 'approval-what' });
    what.append(Object.assign(document.createElement('b'), { textContent: e.tool }));
    el.append(what);
    // the whole input, every line, in a box that scrolls: the author reads all of what they allow
    if (e.summary) el.append(Object.assign(document.createElement('pre'), { className: 'approval-input', tabIndex: 0, textContent: e.summary }));
    const actions = Object.assign(document.createElement('div'), { className: 'approval-actions' });
    for (const [decision, label] of [['allow', 'Permitir'], ['deny', 'Negar']]) {
      const button = Object.assign(document.createElement('button'), { type: 'button', className: `btn${decision === 'allow' ? ' primary' : ''}`, textContent: label });
      button.addEventListener('click', async () => {
        for (const b of actions.querySelectorAll('button')) b.disabled = true;
        const { status, data } = await studio.api(`/api/approvals/${e.id}`, { decision });
        if (status !== 200) {
          studio.ui.toast(data?.message ?? `O studio não aceitou a resposta (erro ${status}).`, 'error');
          for (const b of actions.querySelectorAll('button')) b.disabled = false;
        }
      });
      actions.append(button);
    }
    el.append(Object.assign(document.createElement('p'), { className: 'approval-why', textContent: e.reason }), actions);
    return studio.chat.append(el);
  }

  const show = (e) => cards.has(e.id) || cards.set(e.id, card(e));
  studio.on('approval', (e) => {
    if (e.state === 'pending') return show(e);
    const el = cards.get(e.id);
    if (!el) return;
    cards.delete(e.id);
    el.dataset.state = e.state;
    const ended = Object.assign(document.createElement('p'), { className: 'approval-state', textContent: ENDED[e.state] ?? e.state });
    ended.setAttribute('role', 'status');
    el.querySelector('.approval-actions').replaceWith(ended);
  });
  // after subscribing, so no card falls between the list and the events
  return studio.api('/api/approvals').then(({ data }) => { for (const e of data ?? []) show(e); });
}
