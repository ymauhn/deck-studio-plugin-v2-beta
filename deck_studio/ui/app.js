// Deck Studio UI: deck frame, picker bridge, chat, and window.studio, the API every UI feature receives.
// Plain module, no framework. Feature modules (ui/features/*.js) load last and get studio as default(studio).
import { markdown } from './markdown.js';

const $ = (id) => document.getElementById(id);
const frame = $('deck-frame');
const pickButton = $('pick');
const conversations = $('conversations');
const message = $('message');
const isTyping = (el) => el?.closest?.('input, textarea, select, [contenteditable]');

// fn(...args) for every listener; one failing listener does not stop the others
const notify = (fns, ...args) => {
  for (const fn of [...fns]) {
    try { fn(...args); } catch (e) { console.error(e); }
  }
};
const listeners = () => {
  const fns = new Set();
  return { fns, subscribe: (fn) => { fns.add(fn); return () => fns.delete(fn); } };
};

// ---------- server: JSON calls and one shared event stream ----------
// GET without a body, POST with one (JSON, or raw for a Blob or ArrayBuffer); always resolves to {status, data}
async function api(path, body, { method, headers } = {}) {
  const raw = body instanceof Blob || body instanceof ArrayBuffer;
  const init = { method: method ?? (body == null ? 'GET' : 'POST'), headers: { ...headers } };
  if (body != null) {
    init.body = raw ? body : JSON.stringify(body);
    if (!raw) init.headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(path, init).catch(() => null);
  if (!res) return { status: 0, data: { message: 'O studio não respondeu. Ele ainda está rodando?' } };
  return { status: res.status, data: await res.json().catch(() => null) };
}

const handlers = new Map(); // event type -> listeners
function on(type, fn) {
  if (!handlers.has(type)) handlers.set(type, listeners());
  return handlers.get(type).subscribe(fn);
}
let held = []; // chat events that come while the conversations are first drawn (see the end of this file)
new EventSource('/api/events').addEventListener('message', (m) => {
  const e = JSON.parse(m.data);
  if (held && e.type === 'chat') held.push(e);
  else notify(handlers.get(e.type)?.fns ?? [], e);
});
// the stream starts with a status event, sent once it is subscribed
const connected = new Promise((resolve) => {
  const off = on('status', () => { off(); resolve(); });
});

// ---------- project: the deck this studio edits, as GET /api/status describes it (studio.project) ----------
const projectReady = api('/api/status').then(({ data }) => {
  const project = data?.project ?? null;
  if (project?.title) { // in the top bar and in the browser tab, so the tabs of two studios can be told apart
    Object.assign($('project'), { textContent: project.title, title: project.title, hidden: false });
    document.title = `${project.title} · Deck Studio`;
  }
  return project;
});

// ---------- picker bridge: direct calls into the (same-origin) deck frame, postMessage back ----------
const picker = () => frame.contentWindow?.studioPicker;
let picking = false;

function setPicking(on, tell = true) {
  picking = on;
  pickButton.setAttribute('aria-pressed', String(on));
  if (tell) picker()?.setMode(on);
}

pickButton.addEventListener('click', () => setPicking(!picking));
document.addEventListener('keydown', (e) => {
  if (e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return;
  if (e.key === 's' || e.key === 'S') {
    e.preventDefault();
    setPicking(!picking);
  }
});

// ---------- selection chips ----------
let selection = [];
const selectionListeners = listeners();

const KIND_LABEL = { table: 'tabela gerada', math: 'fórmula' };

function chip(s) {
  const li = document.createElement('li');
  li.className = `chip ${s.kind}`;
  if (s.kind === 'table') li.title = 'Tabela gerada a partir da dissertação: só leitura';
  if (s.kind === 'tex') { // a line of a hand-written Beamer deck: its frame title and file:line
    li.append(Object.assign(document.createElement('b'), { textContent: s.title || 'frame' }), ' ',
      Object.assign(document.createElement('code'), { textContent: `${s.file.split('/').pop()}:${s.line}` }));
    return li;
  }
  li.append(Object.assign(document.createElement('b'), { textContent: s.slideId }), ` ${s.component ?? KIND_LABEL[s.kind] ?? s.tag} `,
    Object.assign(document.createElement('code'), { textContent: `${s.part}:${s.loc.line}` }));
  return li;
}

function setSelection(list) {
  selection = list;
  $('chips').replaceChildren(...selection.map(chip));
  notify(selectionListeners.fns, selection);
}

function clearSelection() {
  setSelection([]);
  picker()?.clear();
}

// After a swap or a reload the slide nodes are new: re-anchor each chip to its box in the new DOM (the picker finds
// it by text, so an edit that shifts lines re-anchors it), and drop a chip whose box is gone, so a chip never keeps
// (or sends) a line the sources no longer have.
function reresolve() {
  const p = picker();
  if (!p?.resolve) return;
  try { setSelection(selection.map((s) => p.resolve(s)).filter(Boolean)); } catch { /* leave the chips as they are */ }
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && selection.length) clearSelection();
});

addEventListener('message', (e) => {
  if (e.origin !== location.origin || e.source !== frame.contentWindow) return;
  if (e.data?.type === 'studio:mode') setPicking(e.data.on, false);
  if (e.data?.type === 'studio:selection') setSelection(e.data.selection);
});

// The deck's place is kept on every change, so that after a reload of this page (F5) the deck opens where it was.
let place = null;
try { place = JSON.parse(sessionStorage.getItem('studio-deck')); } catch { /* none kept */ }
function deckLoaded() {
  if (place) frame.contentWindow.deck?.go(place.slide, place.fragment);
  place = null;
  frame.contentDocument.addEventListener('deck:change', (e) => {
    try { sessionStorage.setItem('studio-deck', JSON.stringify(e.detail)); } catch { /* not kept */ }
  });
}
if (frame.contentDocument?.readyState === 'complete' && frame.contentWindow.deck) deckLoaded(); // loaded before us

// picking waits while the deck rebuilds, so that no box its sources no longer have is picked
let building = false;
function setBuilding(on) {
  building = on;
  picker()?.pause(on);
}
on('build', (b) => setBuilding(!!b.running));
on('status', (s) => setBuilding(!!s.build?.running));

// a (re)loaded deck starts with the picker off and without focus: hand it the mode and the keyboard
frame.addEventListener('load', () => {
  deckLoaded();
  setPicking(picking);
  setBuilding(building);
  frame.contentWindow.focus();
});

// ---------- deck ----------
const deck = {
  frame,
  win: () => frame.contentWindow,
  go: (slide, step = 0) => deck.win().deck.go(slide, step),
  // null until the deck's engine starts: while its page still loads, its window.deck is the #deck element
  state: () => {
    const engine = deck.win()?.deck;
    return typeof engine?.state === 'function' ? engine.state() : null;
  },
  // reloads the deck page and puts it back at the same slide and step
  reload() {
    const at = deck.state();
    return new Promise((resolve) => {
      frame.addEventListener('load', () => {
        if (at && deck.state()) deck.go(at.slide, at.fragment);
        reresolve();  // the chips' boxes are new nodes now
        resolve();
      }, { once: true });
      deck.win().location.reload();
    });
  },
};
on('deck-reload', () => deck.reload());

// ---------- build state: shown in the deck bar, so a failed rebuild is never silent ----------
const buildStatus = Object.assign(document.createElement('p'), { className: 'build-status', hidden: true });
buildStatus.setAttribute('role', 'status');
document.querySelector('.deck-bar').append(buildStatus);
const lastLine = (text) => (text || '').trim().split('\n').filter(Boolean).pop() ?? '';
function showBuild(b) {
  if (!b) return;
  if (b.running) Object.assign(buildStatus, { hidden: false, textContent: 'Compilando…' });
  else if (b.ok) Object.assign(buildStatus, { hidden: true, textContent: '' });
  else Object.assign(buildStatus, { hidden: false, textContent: `A compilação falhou. ${lastLine(b.error)}`.trim() });
  buildStatus.dataset.state = b.running ? 'running' : b.ok ? 'ok' : 'error';
}
on('build', (b) => showBuild(b));
on('status', (s) => showBuild(s.build));

// ---------- page parts that features add ----------
function toast(text, kind = 'info') {
  let box = document.querySelector('.toasts');
  if (!box) document.body.append(box = Object.assign(document.createElement('div'), { className: 'toasts' }));
  const el = Object.assign(document.createElement('p'), { className: `toast ${kind}`, textContent: text });
  el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  box.append(el);
  setTimeout(() => el.remove(), kind === 'error' ? 10_000 : 5_000);
  return el;
}

// an in-page confirmation (never window.confirm); resolves to true only on "Confirmar"
function confirmInPage(text) {
  const dialog = Object.assign(document.createElement('dialog'), { className: 'confirm' });
  const question = Object.assign(document.createElement('p'), { id: `confirm-${Date.now()}`, textContent: text });
  dialog.setAttribute('aria-labelledby', question.id);
  const form = Object.assign(document.createElement('form'), { method: 'dialog' });
  form.append(Object.assign(document.createElement('button'), { className: 'btn', value: 'cancel', textContent: 'Cancelar' }),
    Object.assign(document.createElement('button'), { className: 'btn primary', value: 'ok', textContent: 'Confirmar' }));
  dialog.append(question, form);
  document.body.append(dialog);
  return new Promise((resolve) => {
    dialog.addEventListener('close', () => {
      resolve(dialog.returnValue === 'ok');
      dialog.remove();
    });
    dialog.showModal();
  });
}

const ui = {
  addToolbarButton({ id, label, title, onClick, pressed }) {
    const button = Object.assign(document.createElement('button'), { id, type: 'button', className: 'btn', textContent: label });
    if (title) button.title = title;
    if (pressed !== undefined) button.setAttribute('aria-pressed', String(pressed));
    if (onClick) button.addEventListener('click', onClick);
    document.querySelector('.deck-bar').append(button);
    return button;
  },
  // side: 'left' (files pane), 'right' (chat pane, above the conversation) or 'bottom' (under the deck)
  addPanel({ id, title, side, element }) {
    const panel = Object.assign(document.createElement('section'), { id, className: `panel ${side}` });
    const heading = Object.assign(document.createElement('h2'), { id: `${id}-h`, textContent: title });
    panel.setAttribute('aria-labelledby', heading.id);
    panel.append(heading, element);
    if (side === 'right') conversations.before(panel);
    else document.querySelector(side === 'left' ? '.pane.files' : '.pane.deck').append(panel);
    return panel;
  },
  toast,
  confirm: confirmInPage,
};

// ---------- chats: one tab and one conversation log per chat ----------
const tabList = $('chat-tabs');
const chats = new Map(); // chat id -> {id, title, model, tab, log}
let chat = null; // the current chat
const writing = new Map(); // turnId -> {bubble, text}: an answer still receiving text

function addChat(c) {
  const log = Object.assign(document.createElement('div'), { id: `log-${c.id}`, className: 'conversation', hidden: true });
  log.setAttribute('role', 'log');
  log.setAttribute('aria-label', 'Conversa');
  const tab = Object.assign(document.createElement('button'), { id: `tab-${c.id}`, type: 'button', className: 'tab', textContent: c.title });
  tab.setAttribute('role', 'tab');
  tab.setAttribute('aria-controls', log.id);
  tab.addEventListener('click', () => select(c.id));
  tab.toggleAttribute('data-running', !!c.running);
  tabList.append(tab);
  conversations.append(log);
  const entry = { ...c, tab, log };
  chats.set(c.id, entry);
  return entry;
}

function select(id) {
  chat = chats.get(id);
  for (const c of chats.values()) {
    c.tab.setAttribute('aria-selected', String(c === chat));
    c.tab.tabIndex = c === chat ? 0 : -1;
    c.log.hidden = c !== chat;
  }
  chat.tab.scrollIntoView({ block: 'nearest', inline: 'nearest' });  // a selected tab past the row's edge comes into view
  chat.log.scrollTop = chat.log.scrollHeight;
  $('model').value = chat.model;
  $('effort').value = chat.effort ?? '';
  $('stop').hidden = !chat.running;
  try { sessionStorage.setItem('studio-chat', id); } catch { /* a reload then opens another chat */ }
}

async function newChat() {
  const { status, data } = await api('/api/chats', {});
  if (status !== 201) return onChat.error({ message: data?.message ?? `O studio não abriu o chat (erro ${status}).` });
  select(addChat(data).id);
}
$('new-chat').addEventListener('click', newChat);

// the tab's name becomes a text field: Enter (or leaving it) saves, Esc cancels
function rename(c = chat) {
  const input = Object.assign(document.createElement('input'), { className: 'tab-name', value: c.title, maxLength: 60 });
  input.setAttribute('aria-label', 'Nome do chat');
  c.tab.hidden = true;
  c.tab.after(input);
  input.select();
  let done = false;
  const finish = async (save, refocus = true) => {
    if (done) return;
    done = true;
    input.remove();
    c.tab.hidden = false;
    if (refocus) c.tab.focus();
    const title = input.value.trim();
    if (!save || !title || title === c.title) return;
    const { status, data } = await api(`/api/chats/${c.id}/title`, { title });
    if (status !== 200) return toast(data?.message ?? `O studio não renomeou o chat (erro ${status}).`, 'error');
    c.title = c.tab.textContent = data.title;
  };
  input.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== 'Escape') return;
    e.preventDefault();
    e.stopPropagation(); // Esc here does not clear the selection
    finish(e.key === 'Enter');
  });
  input.addEventListener('blur', () => finish(true, false));
}

// a chat with messages goes only after an in-page confirmation; the next tab (or a new chat) takes its place
async function closeChat(c = chat) {
  if (c.log.children.length && !(await confirmInPage(`Fechar o chat "${c.title}"? A conversa sai da lista.`))) return;
  const { status, data } = await api(`/api/chats/${c.id}`, null, { method: 'DELETE' });
  if (status !== 200) return toast(data?.message ?? `O studio não fechou o chat (erro ${status}).`, 'error');
  const ids = [...chats.keys()];
  const i = ids.indexOf(c.id);
  c.tab.remove();
  c.log.remove();
  chats.delete(c.id);
  if (c !== chat) return;
  const next = ids[i + 1] ?? ids[i - 1];
  if (next) select(next);
  else await newChat();
}

$('rename-chat').addEventListener('click', () => rename());
$('close-chat').addEventListener('click', () => closeChat());
tabList.addEventListener('dblclick', (e) => e.target.getAttribute('role') === 'tab' && rename());
// arrow keys move between tabs, F2 renames
tabList.addEventListener('keydown', (e) => {
  if (e.target.getAttribute('role') !== 'tab') return;
  if (e.key === 'F2') return rename();
  const ids = [...chats.keys()];
  const i = ids.indexOf(chat.id);
  const next = { ArrowRight: ids[(i + 1) % ids.length], ArrowLeft: ids.at(i - 1), Home: ids[0], End: ids.at(-1) }[e.key];
  if (!next) return;
  e.preventDefault();
  select(next);
  chat.tab.focus();
});

// A page opens on the chat it showed before a reload, else on the chat its link names (#chat=<id>: an imported
// project's first request). After a restart (chats came back from disk) it opens on the chat used last; otherwise on
// the last chat if it is still empty, or on a new one.
function landing(list) {
  let shown = null;
  try { shown = sessionStorage.getItem('studio-chat'); } catch { /* none */ }
  const linked = new URLSearchParams(location.hash.slice(1)).get('chat');
  const last = list.at(-1);
  const recent = list.some((c) => c.restored) && list.reduce((a, b) => (b.updated > a.updated ? b : a));
  return list.find((c) => c.id === shown) ?? list.find((c) => c.id === linked) ?? (recent || (last?.messages.length ? null : last));
}

const chatReady = (async () => {
  await connected; // so no chat event falls between the list and the stream
  const list = (await api('/api/chats')).data ?? [];
  list.forEach(addChat);
  const first = landing(list);
  if (first) select(first.id);
  else await newChat();
  return list;
})();
$('model').addEventListener('change', (e) => {
  chat.model = e.target.value;
  api(`/api/chats/${chat.id}/model`, { model: chat.model });
});
$('effort').addEventListener('change', (e) => {
  chat.effort = e.target.value;
  api(`/api/chats/${chat.id}/effort`, { effort: chat.effort });
});

let drawn = false; // features append while they load; those cards go after the redrawn conversations
const later = [];

// studio.chat.append(element, chatId?): adds it to that chat's conversation (the current one by default)
function append(el, chatId = chat?.id) {
  if (!drawn) {
    later.push([el, chatId]);
    return el;
  }
  const log = chats.get(chatId)?.log;
  if (!log) return el;
  log.append(el);
  log.scrollTop = log.scrollHeight;
  return el;
}

function bubble(kind, label, content, chatId) {
  const el = Object.assign(document.createElement('article'), { className: `msg ${kind}` });
  el.setAttribute('aria-label', label);
  el.append(Object.assign(document.createElement('p'), { textContent: content }));
  return append(el, chatId);
}

// a chat runs from its message to its turn-end: its tab shows it, and the Stop button belongs to the current chat
function running(chatId, on) {
  const c = chats.get(chatId);
  if (!c) return;
  c.running = on;
  c.tab.toggleAttribute('data-running', on);
  if (c === chat) $('stop').hidden = !on;
}

$('stop').addEventListener('click', async () => {
  $('stop').disabled = true;
  const { status, data } = await api(`/api/chats/${chat.id}/interrupt`, {});
  $('stop').disabled = false;
  if (status !== 200) toast(data?.message ?? `O studio não parou o pedido (erro ${status}).`, 'error');
});

const onChat = {
  user: (e) => {
    if (!e.replay) running(e.chatId, true);
    const b = bubble('user', 'Você', e.text, e.chatId);
    if (!e.selection?.length) return;
    const sent = Object.assign(document.createElement('ul'), { className: 'chips' });
    sent.append(...e.selection.map(chip));
    b.prepend(sent);
  },
  // the agent writes Markdown: its answer shows as a safe subset of it (markdown.js), drawn again as text streams in
  'text-delta': (e) => {
    if (!writing.has(e.turnId)) writing.set(e.turnId, { bubble: bubble('assistant', 'Claude', '', e.chatId), text: '' });
    const w = writing.get(e.turnId);
    w.text += e.text;
    w.bubble.innerHTML = markdown(w.text);
  },
  // the full text of a block replaces its deltas and closes the bubble
  text: (e) => {
    (writing.get(e.turnId)?.bubble ?? bubble('assistant', 'Claude', '', e.chatId)).innerHTML = markdown(e.text);
    writing.delete(e.turnId);
  },
  // what went wrong and what to do next; the technical detail (the SDK's own words) stays folded below
  error: (e) => {
    const b = bubble('error', 'Erro', e.message, e.chatId);
    if (e.detail) {
      const detail = document.createElement('details');
      detail.append(Object.assign(document.createElement('summary'), { textContent: 'Detalhe técnico' }),
        Object.assign(document.createElement('p'), { textContent: e.detail }));
      b.append(detail);
    }
    if (!e.replay) b.setAttribute('role', 'alert');
  },
  notice: (e) => bubble('notice', 'Aviso', e.message, e.chatId), // the studio's own word on the turn, not an error
  'turn-end': (e) => {
    writing.delete(e.turnId);
    if (!e.replay) running(e.chatId, false);
  },
};
on('chat', (e) => onChat[e.kind]?.(e));

const percent = (v) => (typeof v === 'number' ? `${Math.round(v * 100)}%` : '–');
let studioBusy = false; // last "busy" the server announced
let sending = false; // a message POST is in flight
on('status', ({ usage, busy }) => {
  $('usage-5h').textContent = `limite de 5 h: ${percent(usage.five_hour)}`;
  $('usage-7d').textContent = `semana: ${percent(usage.seven_day)}`;
  studioBusy = busy;
  if (!busy && !$('waiting').hidden) send(); // our turn: the message that waited goes out now
});

message.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    $('composer').requestSubmit();
  }
});

// sends text on the current chat with a selection (by default the one picked now); resolves to {status, data},
// where 202 means the turn started and 409 that another turn is running
async function sendMessage(text, { selection: boxes = selection } = {}) {
  await chatReady;
  return api(`/api/chats/${chat.id}/messages`, { text, selection: boxes });
}

// One turn runs at a time across chats: a busy studio answers 409 and the message waits for its turn,
// which the next "not busy" status announces.
async function send() {
  const text = message.value.trim();
  if (!text || sending) return;
  sending = true;
  const { status, data } = await sendMessage(text).finally(() => { sending = false; });
  $('waiting').hidden = status !== 409;
  if (status === 202) {
    message.value = '';
    clearSelection();
  } else if (status === 409) {
    if (!studioBusy) setTimeout(send, 500); // the running turn ended while we were asking
  } else {
    onChat.error({ message: data?.message ?? `O studio não aceitou a mensagem (erro ${status}).` });
  }
}

$('composer').addEventListener('submit', (e) => {
  e.preventDefault();
  send();
});

// ---------- mode: the HTML deck or a Beamer view ----------
let mode = 'html';
const modeListeners = listeners();

// ---------- window.studio ----------
const studio = {
  api,
  on,
  // {title, format, startMode, beamerStart, provenance, jobs: [names]}: set before the features load
  project: null,
  selection: { get: () => selection, set: setSelection, subscribe: selectionListeners.subscribe, clear: clearSelection },
  deck,
  ui,
  composer: {
    insert(text) {
      message.setRangeText(text, message.selectionStart, message.selectionEnd, 'end');
      message.focus();
    },
    setText(text) { message.value = text; },
    focus: () => message.focus(),
  },
  chat: { send: sendMessage, current: () => chat, append },
  mode: {
    get: () => mode,
    set(value) {
      if (value !== 'html' && value !== 'beamer') throw new Error(`modo desconhecido: ${value}`);
      if (value === mode) return;
      mode = value;
      notify(modeListeners.fns, mode);
    },
    subscribe: modeListeners.subscribe,
  },
};
window.studio = studio;

// ---------- features ----------
async function loadFeatures() {
  const { data } = await api('/api/ui-features');
  for (const href of data?.css ?? []) document.head.append(Object.assign(document.createElement('link'), { rel: 'stylesheet', href }));
  for (const url of data?.app ?? []) {
    try {
      await (await import(url)).default?.(studio);
    } catch (e) {
      console.error(`Deck Studio: ${url} não carregou.`, e);
    }
  }
}

// Every conversation is drawn again from its kept events, through every chat handler, so the features' cards come
// back too. Then the events held meanwhile go out, except those already drawn and the text deltas (the text follows).
const list = await chatReady;
studio.project = await projectReady;
await loadFeatures();
drawn = true;
const toChat = (e) => notify(handlers.get('chat')?.fns ?? [], e);
for (const c of list) for (const e of c.messages) toChat({ ...e, replay: true });
for (const [el, chatId] of later.splice(0)) append(el, chatId);
const drawnUpTo = new Map(list.map((c) => [c.id, c.messages.length]));
for (const e of held) if (!(e.seq <= drawnUpTo.get(e.chatId)) && e.kind !== 'text-delta') toChat(e);
held = null;
document.body.dataset.ready = '';
