// Turn cards: every direct edit (an `edit` event) and every agent turn that changed files (a `chat` turn-end
// with files) gets a card in the conversation, with its files, "Ver diff" (the turn's diff) and "Desfazer".
const make = (tag, className = '', text) => Object.assign(document.createElement(tag), { className }, text != null && { textContent: text });

// one span per diff line, by kind; as textContent, every tag in the diff stays text
const kind = (line) => (/^(---|\+\+\+) /.test(line) ? 'head' : { '+': 'add', '-': 'del', '@': 'hunk' }[line[0]] ?? '');
const lines = (diff) => diff.replace(/\n$/, '').split('\n').map((l) => make('span', kind(l), `${l.replace(/\r$/, '')}\n`));

export default async function (studio) {
  const shown = new Map(); // turnId -> marks its card undone
  let undone = new Set();
  studio.on('edit', (e) => card(e.turnId, e.label, e.files));
  studio.on('chat', (e) => {
    if (e.kind === 'turn-end' && e.files?.length) card(e.turnId, 'Arquivos alterados', e.files, e.chatId);
  });
  // after a page reload: the direct edits get their cards again (agent turns come back with their chat), and
  // every card of a turn already undone says so. Awaited: app.js draws the conversations, then these cards, and
  // only then marks the page ready
  const { status, data } = await studio.api('/api/turns');
  if (status === 200) {
    undone = new Set(data.filter((t) => t.undone).map((t) => t.turnId));
    for (const t of data) {
      if (t.kind === 'edit') card(t.turnId, t.label, t.files);
      else if (t.undone) shown.get(t.turnId)?.();
    }
  }

  function card(turnId, label, files, chatId) {
    if (shown.has(turnId)) return; // drawn from /api/turns and from its live event: once
    const article = make('article', 'msg turn');
    article.setAttribute('aria-label', 'Alterações');
    const list = make('ul', 'turn-files');
    for (const f of files) {
      const item = make('li');
      item.append(make('code', '', f));
      list.append(item);
    }
    const diff = Object.assign(make('pre', 'diff'), { id: `diff-${turnId}`, hidden: true, tabIndex: 0 });
    const undo = Object.assign(make('button', 'btn', 'Desfazer'), { type: 'button' });
    const show = Object.assign(make('button', 'btn', 'Ver diff'), { type: 'button' });
    show.setAttribute('aria-expanded', 'false');
    show.setAttribute('aria-controls', diff.id);
    const actions = make('div', 'turn-actions');
    actions.append(undo, show);
    const note = make('p', 'turn-note');
    note.setAttribute('role', 'status');
    article.append(make('p', 'turn-label', label), list, diff, actions, note);
    const say = (text, error = false) => {
      note.textContent = text;
      note.classList.toggle('error', error);
    };
    const markUndone = () => {
      undo.disabled = true;
      say('Desfeito.');
    };
    shown.set(turnId, markUndone);
    if (undone.has(turnId)) markUndone();

    show.addEventListener('click', async () => {
      const opening = diff.hidden;
      if (opening) {
        const { status, data } = await studio.api(`/api/turns/${turnId}/diff`);
        if (status !== 200) return say(data?.message ?? `O diff não veio (erro ${status}).`, true);
        diff.replaceChildren(...lines(data.diff));
      }
      diff.hidden = !opening;
      show.setAttribute('aria-expanded', String(opening));
    });

    // the server restores the files and rebuilds; the deck then reloads at the same slide and step
    undo.addEventListener('click', async () => {
      undo.disabled = true;
      const { status, data } = await studio.api(`/api/turns/${turnId}/undo`, {});
      if (status === 200) return markUndone();
      undo.disabled = false;
      say(data?.message ?? `O studio não desfez este pedido (erro ${status}).`, true);
    });

    studio.chat.append(article, chatId);
  }
}
