// Comment batches: "Comentar (C)" stores a comment with the selected boxes; the deck draws numbered pins on them
// (ui/deck/comments.js); a panel lists them by slide, with go to, edit and delete, and "Aplicar N comentários"
// sends them all in one chat message.
const isTyping = (el) => el?.closest?.('input, textarea, select, [contenteditable]');
const isC = (e) => (e.key === 'c' || e.key === 'C') && !e.ctrlKey && !e.metaKey && !e.altKey && !isTyping(e.target);
const make = (tag, props) => Object.assign(document.createElement(tag), props);

export default function comments(studio) {
  const { api, ui, selection } = studio;

  // a one-line comment field: Enter saves through save(text) -> {status, data}, Esc gives up; then done(saved)
  function commentField(value, save, done) {
    const input = make('input', { className: 'comment-field', value, placeholder: 'Comentário para as caixas selecionadas' });
    input.setAttribute('aria-label', 'Comentário');
    input.addEventListener('keydown', async (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation(); // Esc closes the field and keeps the selection
        return done(false);
      }
      if (e.key !== 'Enter' || e.isComposing || input.readOnly || !input.value.trim()) return;
      input.readOnly = true;
      const { status, data } = await save(input.value);
      input.readOnly = false;
      if (status < 200 || status >= 300) return ui.toast(data?.message ?? `O comentário não foi salvo (erro ${status}).`, 'error');
      done(true);
    });
    return input;
  }

  // ---------- the server's list, in slide order: a comment's number is its place in it ----------
  let list = [];
  let busy = false; // a turn is running: the batch waits
  const items = make('ol', { className: 'comment-list' });
  const panel = ui.addPanel({ id: 'comments', title: 'Comentários', side: 'right', element: items });
  const applyButton = make('button', { type: 'button', className: 'btn primary apply', onclick: apply });
  panel.append(applyButton);
  const pin = () => studio.deck.win()?.studioComments?.show(list);

  function show(comments) {
    list = comments;
    pin();
    panel.hidden = !list.length;
    items.replaceChildren(...list.map(item));
    const n = list.filter((c) => !c.sent).length;
    applyButton.hidden = !n;
    applyButton.textContent = `Aplicar ${n} ${n === 1 ? 'comentário' : 'comentários'}`;
    applyButton.disabled = busy;
  }

  let pushed = false; // an event came before the first list arrived
  studio.on('comments', (e) => {
    pushed = true;
    show(e.comments);
  });
  api('/api/comments').then(({ status, data }) => status === 200 && !pushed && show(data));
  studio.deck.frame.addEventListener('load', pin); // a reloaded deck starts without pins
  studio.on('status', (e) => {
    busy = e.busy;
    applyButton.disabled = busy;
  });

  function item(c, i) {
    const li = make('li', { className: `comment${c.sent ? ' sent' : ''}` });
    const where = make('p', { className: 'where', textContent: c.selection.map((s) => `${s.slideId} ${s.component ?? s.tag}`).join(', ') });
    if (c.sent) where.append(' · ', make('span', { className: 'state', textContent: 'enviado' }));
    const text = make('p', { className: 'text', textContent: c.text });
    const action = (label, onclick) => make('button', { type: 'button', textContent: label, onclick });
    const [first] = c.selection;
    const edit = action('Editar', () => {
      const input = commentField(c.text, (t) => api(`/api/comments/${c.id}`, { text: t }, { method: 'PATCH' }),
        (saved) => saved || input.replaceWith(text)); // a saved text comes back with the comments event
      text.replaceWith(input);
      input.focus();
    });
    edit.disabled = Boolean(c.sent); // the agent already has this text
    const actions = make('div', { className: 'actions' });
    actions.append(
      action('Ir ao slide', () => {
        studio.deck.go(first.slide, first.step);
        studio.deck.win().focus();
      }),
      edit,
      action('Excluir', () => api(`/api/comments/${c.id}`, null, { method: 'DELETE' })));
    li.append(make('b', { className: 'n', textContent: i + 1 }), where, text, actions);
    return li;
  }

  // One chat turn for the whole batch: every commented box with its comment. The server marks the comments with
  // that turn (by commentId) and clears them when it ends without an error.
  // ponytail: the chat route keeps the first 50 boxes: later comments wait for another batch, one cut there goes short
  async function apply() {
    const boxes = list.filter((c) => !c.sent).flatMap((c) => c.selection.map((s) => ({ ...s, comment: c.text, commentId: c.id })));
    applyButton.disabled = true;
    const { status, data } = await studio.chat.send('Aplique os comentários: cada caixa da seleção traz o meu pedido no campo "comment".', { selection: boxes });
    if (status === 202) return;
    applyButton.disabled = busy;
    ui.toast(status === 409 ? 'Outro pedido está em andamento. Aplique os comentários quando ele terminar.'
      : data?.message ?? `Os comentários não foram enviados (erro ${status}).`, 'error');
  }

  // ---------- a new comment on the selection ----------
  const button = ui.addToolbarButton({ id: 'comment', label: 'Comentar (C)', title: 'Comentar as caixas selecionadas', onClick: write });
  button.setAttribute('aria-keyshortcuts', 'C');
  let field = null; // the new comment's field, while it is open

  function write() {
    if (field) return field.focus();
    if (!selection.get().length) return;
    field = commentField('', (text) => api('/api/comments', { text, selection: selection.get() }), (saved) => {
      close();
      if (saved) selection.clear(); // the boxes carry the comment now
    });
    button.after(field);
    field.focus();
  }

  function close() {
    field?.remove();
    field = null;
    studio.deck.win()?.focus();
  }

  const enable = (boxes) => {
    button.disabled = !boxes.length;
    if (!boxes.length && field) close();
  };
  enable(selection.get());
  selection.subscribe(enable);

  // C on the studio page, or in the deck (ui/deck/comments.js posts studio:comment)
  document.addEventListener('keydown', (e) => {
    if (!isC(e)) return;
    e.preventDefault();
    write();
  });
  addEventListener('message', (e) => {
    if (e.origin === location.origin && e.source === studio.deck.win() && e.data?.type === 'studio:comment') write();
  });
}
