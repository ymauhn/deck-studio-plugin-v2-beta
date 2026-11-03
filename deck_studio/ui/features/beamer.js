// Beamer mode: the "HTML | Beamer" switch in the top bar and, laid over the deck frame, the kit's Beamer projects:
// a project's pages (rendered by the server at the screen's pixel ratio), with thumbnails and the page keys.
// A click selects: in a hand-written deck the TeX line there, whose frame opens in the "Fonte LaTeX" pane (saved as an
// undoable turn, then compiled); in the generated deck the HTML box at the same slide, step and point.
const KIND = { handwritten: 'escrito à mão', generated: 'gerado do HTML' };
const KEYS = { ArrowLeft: -1, PageUp: -1, ArrowRight: 1, PageDown: 1 };
const make = (tag, props = {}) => Object.assign(document.createElement(tag), props);
const seconds = (ms) => `${(ms / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`;

export default function beamer(studio) {
  // ---------- the switch ----------
  const group = make('div', { className: 'mode-switch' });
  group.setAttribute('role', 'group');
  group.setAttribute('aria-label', 'Modo');
  const switches = {};
  for (const [mode, label] of [['html', 'HTML'], ['beamer', 'Beamer']]) {
    switches[mode] = make('button', { type: 'button', textContent: label, onclick: () => studio.mode.set(mode) });
    group.append(switches[mode]);
  }
  document.querySelector('header.top h1').after(group);

  // ---------- the view: laid over the deck frame, which stays loaded (and sized) under it ----------
  const view = make('section', { className: 'beamer-view', hidden: true, tabIndex: -1 });
  view.setAttribute('aria-label', 'Beamer');
  const listHead = make('h3', { id: 'beamer-projects-h', textContent: 'Projetos Beamer' });
  const list = make('ul', { className: 'beamer-projects' });
  list.setAttribute('aria-labelledby', listHead.id);
  const chooser = make('div', { className: 'beamer-chooser' });
  chooser.append(listHead, list);

  const pages = make('div', { className: 'beamer-pages', hidden: true });
  const title = make('b', { className: 'beamer-title' });
  const head = make('div', { className: 'beamer-head' });
  // back to the list of decks ("Projetos", in the top bar, is Deck Studio's projects)
  head.append(make('button', { type: 'button', className: 'btn', textContent: 'Voltar à lista', onclick: () => close() }), title);
  const errors = make('ul', { className: 'beamer-errors', hidden: true });
  errors.setAttribute('role', 'alert');
  const stage = make('div', { className: 'beamer-stage' });
  const image = make('img', { className: 'beamer-page', alt: '' });
  stage.append(image);
  const strip = make('ol', { className: 'beamer-strip' });
  strip.setAttribute('aria-label', 'Páginas');
  pages.append(head, errors, stage, strip);
  view.append(chooser, pages);
  document.querySelector('.pane.deck').append(view);

  const frame = studio.deck.frame;
  const fit = () => Object.assign(view.style, {
    left: `${frame.offsetLeft}px`, top: `${frame.offsetTop}px`, width: `${frame.offsetWidth}px`, height: `${frame.offsetHeight}px`,
  });
  new ResizeObserver(fit).observe(frame);
  // A reloaded deck takes the focus (app.js), as after any edit that rebuilds the HTML. Under the Beamer view it
  // gives it back to where it was, so typing never lands in the hidden deck.
  let focused = null;
  document.addEventListener('focusin', (e) => { if (e.target !== frame) focused = e.target; });
  frame.addEventListener('load', () => {
    if (studio.mode.get() === 'beamer') (focused?.isConnected && !focused.closest('[hidden]') ? focused : view).focus();
  });

  // the deck bar's part in Beamer mode (the HTML deck's tools hide meanwhile)
  const bar = make('div', { className: 'beamer-bar', hidden: true });
  const status = make('p', { className: 'beamer-status' });
  status.setAttribute('role', 'status');
  // the generated deck follows the HTML through the beamer job (its log shows in Tarefas, as from the top bar)
  const regenerate = make('button', {
    type: 'button', className: 'btn', textContent: 'Regenerar Beamer', title: 'Gera de novo a versão Beamer a partir do deck',
    async onclick() {
      regenerate.disabled = true;
      const { status: code, data } = await studio.api('/api/jobs/beamer', {});
      if (code === 202) return;
      regenerate.disabled = false;
      studio.ui.toast(data?.message ?? `A tarefa não começou (erro ${code}).`, 'error');
    },
  });
  // a project's own deck (studio.project.beamerStart) is its PDF: the one of its last good compile of the whole deck
  const pdf = make('a', {
    className: 'btn', textContent: 'Abrir PDF', title: 'Abre o PDF da última compilação do deck', target: '_blank', rel: 'noopener', hidden: true,
  });
  bar.append(status, pdf, regenerate);
  document.querySelector('.deck-bar').append(bar);

  // ---------- projects ----------
  let project = null; // the open project, as the server describes it: {id, kind, rel, view, running, last}
  const latest = {}; // the last `beamer` event of each project, open or not
  let page = 1;
  // a Beamer project starts in Beamer mode (see the end) on its deck, once: then the list is the way back
  const beamerFirst = studio.project?.startMode === 'beamer';
  let start = beamerFirst ? studio.project.beamerStart : null;

  async function showProjects() {
    const { status: code, data } = await studio.api('/api/beamer/projects');
    if (code !== 200) return studio.ui.toast(data?.message ?? `Os projetos Beamer não vieram (erro ${code}).`, 'error');
    const first = start && data.find((p) => p.rel === start);
    start = null;
    if (first) return open(first);
    list.replaceChildren(...data.map((p) => {
      const parts = p.rel.split('/');
      const button = make('button', { type: 'button', className: 'project', onclick: () => open(p) });
      button.append(make('b', { textContent: parts.pop() }), ' ', make('span', { textContent: `${parts.join('/')} · ${KIND[p.kind]}` }));
      const li = make('li');
      li.append(button);
      return li;
    }));
    if (!data.length) list.append(make('li', { className: 'empty', textContent: 'Nenhum projeto Beamer neste kit.' }));
  }

  async function open(p) {
    const before = latest[p.id];
    const { status: code, data } = await studio.api(`/api/beamer/projects/${p.id}/open`, {});
    if (code !== 200) return studio.ui.toast(data?.message ?? `O projeto não abriu (erro ${code}).`, 'error');
    project = data;
    page = 1;
    title.textContent = project.rel;
    regenerate.hidden = project.kind !== 'generated';
    panel.hidden = chooser.hidden = true;
    pages.hidden = bar.hidden = false;
    showStatus();
    showView();
    view.focus();
    // a compile that went on while the answer came (the start mode opens the deck as the studio compiles it): its
    // events came before `project` was set. The latest one shows; any state after it comes as an event too
    if (latest[p.id] !== before) follow(latest[p.id]);
  }

  studio.on('job', async (e) => {
    if (e.name !== 'beamer') return;
    regenerate.disabled = e.state === 'running';
    if (e.state !== 'ok' || project?.kind !== 'generated') return;
    const { status: code, data } = await studio.api(`/api/beamer/projects/${project.id}/open`, {});
    if (code === 200 && data.id === project?.id && data.view?.version !== project.view?.version) {
      project = data;
      showView(); // a new PDF: its pages, from the same page on
    }
  });

  function close() {
    project = null;
    pages.hidden = bar.hidden = panel.hidden = true;
    chooser.hidden = false;
    showProjects();
  }

  // ---------- pages ----------
  const pageUrl = (n, width) => `/api/beamer/projects/${project.id}/pages/${n}?v=${project.view.version}&w=${width}`;

  function showView() {
    const count = project.view?.pages ?? 0;
    strip.replaceChildren(...Array.from({ length: count }, (_, i) => {
      const button = make('button', { type: 'button', onclick: () => showPage(i + 1) });
      button.setAttribute('aria-label', `Página ${i + 1}`);
      button.append(make('img', { alt: '', loading: 'lazy', src: pageUrl(i + 1, Math.round(96 * devicePixelRatio)) }));
      const li = make('li');
      li.append(button);
      return li;
    }));
    image.hidden = !count;
    showPage(page);
  }

  function showPage(n) {
    const count = project?.view?.pages;
    if (!count || !stage.clientWidth) return;
    page = Math.min(Math.max(n, 1), count);
    // the screen's own pixels: the server renders the page at that width (in steps, so resizing reuses images)
    image.src = pageUrl(page, Math.ceil((stage.clientWidth * devicePixelRatio) / 160) * 160);
    image.alt = `Página ${page} de ${count}`;
    strip.querySelectorAll('button').forEach((b, i) => {
      if (i + 1 === page) {
        b.setAttribute('aria-current', 'true');
        b.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      } else b.removeAttribute('aria-current');
    });
  }
  new ResizeObserver(() => showPage(page)).observe(stage);

  // a click selects what is there: a TeX line, with its frame's source in the pane under the view
  image.addEventListener('click', async (e) => {
    const r = image.getBoundingClientRect();
    const at = { page, x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height };
    const { status: code, data } = await studio.api(`/api/beamer/projects/${project.id}/click`, at);
    if (code !== 200) return studio.ui.toast(data?.message ?? `O clique não achou a fonte (erro ${code}).`, 'error');
    const picked = project.kind === 'generated' ? await htmlBox(data) : data.selection;
    if (!picked) return studio.ui.toast('Neste ponto do slide HTML não há caixa para selecionar.', 'error');
    studio.selection.set(e.shiftKey ? [...studio.selection.get(), picked] : [picked]);
    if (data.source) showSource(data.source);
  });

  // The generated deck is a view of the HTML deck: the deck under this view goes to the same slide and step, and its
  // picker gives the box at the same point, once the slide's transitions (if any) have settled.
  async function htmlBox({ slide, step, x, y }) {
    const win = studio.deck.win();
    if (!studio.deck.state()) return null; // the deck is reloading
    studio.deck.go(slide, step);
    await Promise.all(win.document.getAnimations().filter((a) => a.transitionProperty).map((a) => a.finished.catch(() => {})));
    return win.studioPicker?.selectionAt(x, y) ?? null;
  }

  // the page keys, from the view (or from nowhere in particular): the chat keeps its own scrolling keys
  document.addEventListener('keydown', (e) => {
    const step = KEYS[e.key];
    const here = e.target === document.body || view.contains(e.target);
    if (!step || !here || !project || studio.mode.get() !== 'beamer' || e.ctrlKey || e.metaKey || e.altKey) return;
    e.preventDefault();
    showPage(page + step);
  });

  // ---------- the LaTeX of the selected frame ----------
  const where = make('p', { className: 'beamer-where' });
  const tex = make('textarea', { className: 'beamer-tex', spellcheck: false, rows: 9 });
  tex.setAttribute('aria-label', 'LaTeX do frame');
  const save = make('button', { type: 'button', className: 'btn primary', textContent: 'Salvar', disabled: true });
  const done = make('button', { type: 'button', className: 'btn', textContent: 'Fechar', onclick: () => { panel.hidden = true; } });
  const actions = make('div', { className: 'beamer-actions' });
  actions.append(save, done);
  const editor = make('div', { className: 'beamer-source' });
  editor.append(where, tex, actions);
  const panel = studio.ui.addPanel({ id: 'beamer-source', title: 'Fonte LaTeX', side: 'bottom', element: editor });
  panel.hidden = true;
  let source = null; // {file, start, end, title, text}: the frame in the pane, as last loaded or saved

  function showSource(s) {
    source = s;
    where.textContent = `${s.file.split('/').pop()}, linhas ${s.start} a ${s.end}${s.title ? ` · ${s.title}` : ''}`;
    tex.value = s.text;
    save.disabled = true;
    panel.hidden = false;
  }
  tex.addEventListener('input', () => { save.disabled = tex.value === source.text; });

  // one undoable turn (its card shows in the chat); the frame alone compiles first, then the whole deck
  async function saveFrame() {
    save.disabled = true;
    const text = tex.value.replace(/^\n+|\n+$/g, ''); // as the server keeps it
    const { status: code, data } = await studio.api(`/api/beamer/projects/${project.id}/frame`,
      { file: source.file, start: source.start, oldText: source.text, newText: text });
    if (code !== 200) {
      save.disabled = false;
      return studio.ui.toast(data?.message ?? `O frame não foi salvo (erro ${code}).`, 'error');
    }
    if (tex.value !== text) tex.value = text;
    showSource({ ...source, ...data.frame, text });
  }
  save.addEventListener('click', saveFrame);
  tex.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
      e.preventDefault();
      if (!save.disabled) saveFrame();
    }
  });

  // after a compile, a pane with nothing typed in it shows the frame as the file has it now (the agent, an undo)
  async function followSource() {
    const shown = source;
    if (panel.hidden || !shown || tex.value !== shown.text) return;
    const q = new URLSearchParams({ file: shown.file, line: shown.start });
    const { status: code, data } = await studio.api(`/api/beamer/projects/${project.id}/frame?${q}`);
    if (code === 200 && source === shown && tex.value === shown.text && data.text !== shown.text) showSource(data);
  }

  // ---------- compiles ----------
  function showStatus() {
    const { running, last, view: shown } = project;
    if (running === 'frame') status.replaceChildren(make('progress'), 'Compilando o frame…');
    else if (running) status.replaceChildren(make('progress'), shown?.frame != null ? 'Prévia do frame · compilando o deck…' : 'Compilando…');
    else if (last) status.textContent = last.ok ? `Compilado em ${seconds(last.ms)}` : 'A compilação falhou.';
    else if (project.kind === 'generated') status.textContent = shown ? 'PDF gerado do HTML' : 'Ainda sem PDF: use Regenerar Beamer.';
    else status.textContent = '';
    pdf.hidden = !(project.rel === studio.project?.beamerStart && shown?.frame === null && !running && last?.ok);
    if (!pdf.hidden) pdf.href = `/api/beamer/projects/${project.id}/pdf?v=${shown.version}`;
    // the last compile's errors stay up, file:line first, until a compile goes through
    const failed = last?.ok === false ? last.errors : [];
    errors.replaceChildren(...failed.map((e) => {
      const li = make('li');
      if (e.file) li.append(make('code', { textContent: `${e.file.split('/').pop()}:${e.line}` }), ' ');
      li.append(e.message);
      return li;
    }));
    errors.hidden = !failed.length;
  }

  function follow(e) {
    if (e.project.id !== project?.id) return;
    const [from, to] = [project.view, e.project.view];
    project = e.project;
    showStatus();
    if (e.state !== 'running') followSource();
    if (to?.version === from?.version) return;
    // the same page across a frame preview (whose pages start at `offset` in the deck) and the whole deck
    if (to?.frame != null && from?.frame == null) page = to.offset ? page - to.offset + 1 : 1;
    else if (to?.frame == null && from?.frame != null && from.offset) page = from.offset + page - 1;
    showView();
  }
  studio.on('beamer', (e) => {
    latest[e.project.id] = e;
    follow(e);
  });

  // ---------- mode ----------
  function showMode(mode) {
    document.body.dataset.mode = mode;
    for (const [m, b] of Object.entries(switches)) b.setAttribute('aria-pressed', String(m === mode));
    view.hidden = mode !== 'beamer';
    if (mode === 'beamer' && !project) showProjects();
  }
  studio.mode.subscribe(showMode);
  showMode(studio.mode.get());
  if (beamerFirst) studio.mode.set('beamer'); // its deck opens (and compiles, if it changed) as from the list
}
