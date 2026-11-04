// Jobs: one top-bar button per job of the deck's config (studio.project.jobs), such as Exportar PDF, Publicar and
// Regenerar Beamer. Each runs on the server in the background; the Tarefas drawer under the deck shows its live log
// from the `job` events, whoever started it.
const LABELS = { beamer: 'Regenerar Beamer', 'export-pdf': 'Exportar PDF', publish: 'Publicar', overleaf: 'Exportar para Overleaf' };
const TITLES = {
  beamer: 'Gera de novo a versão Beamer a partir do deck',
  'export-pdf': 'Compila o deck limpo e grava o PDF',
  publish: 'Compila o deck limpo e atualiza o link do Netlify',
  overleaf: 'Compacta a pasta do Beamer num .zip para abrir no Overleaf',
};

const seconds = (ms) => `${(ms / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`;

export default function (studio) {
  const bar = Object.assign(document.createElement('div'), { className: 'jobs-bar' });
  document.querySelector('header.top').append(bar);
  const buttons = {};
  // the known jobs in their usual order, then any other job of the config under its own name
  const jobs = studio.project?.jobs ?? [];
  for (const name of [...Object.keys(LABELS).filter((n) => jobs.includes(n)), ...jobs.filter((n) => !(n in LABELS))]) {
    buttons[name] = Object.assign(document.createElement('button'), { type: 'button', className: `btn ${name}`, textContent: LABELS[name] ?? name, title: TITLES[name] ?? '' });
    buttons[name].addEventListener('click', () => (name === 'publish' ? publish() : start(name)));
    bar.append(buttons[name]);
  }

  // a project of its own (HTML, made by Deck Studio) without a site yet: register one, and Publicar shows
  if (studio.project?.registerSite) {
    const register = Object.assign(document.createElement('button'), {
      type: 'button', className: 'btn register-site', textContent: 'Cadastrar link de publicação',
      title: 'Liga este projeto a um site do Netlify; depois, Publicar atualiza esse site',
    });
    register.addEventListener('click', () => registerSite());
    bar.append(register);
  }

  async function registerSite() {
    const dialog = Object.assign(document.createElement('dialog'), { className: 'settings register-dialog' });
    dialog.setAttribute('aria-label', 'Cadastrar link de publicação');
    dialog.innerHTML = `<h2>Cadastrar link de publicação</h2>
      <form method="dialog">
        <p class="settings-row"><label for="site-name">Nome do site no Netlify</label>
          <input id="site-name" required pattern="[a-z0-9\\-]+" placeholder="minha-apresentacao"><span>.netlify.app</span></p>
        <fieldset><legend>O site</legend>
          <label><input type="radio" name="site-kind" value="existing" checked> já existe na minha conta do Netlify</label>
          <label><input type="radio" name="site-kind" value="create"> criar um site novo com esse nome</label>
        </fieldset>
        <p class="small">O login do Netlify é o desta máquina (npx netlify login). O site sai com noindex.</p>
        <div class="settings-actions"><button type="button" class="btn" value="cancel">Cancelar</button>
          <button type="submit" class="btn primary">Cadastrar</button></div>
      </form>`;
    document.body.append(dialog);
    dialog.querySelector('button[value="cancel"]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => dialog.remove());
    dialog.querySelector('form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const name = dialog.querySelector('#site-name').value.trim().toLowerCase();
      const create = dialog.querySelector('input[name="site-kind"]:checked').value === 'create';
      if (create && !(await studio.ui.confirm(`Criar o site ${name}.netlify.app no Netlify? Ele fica no ar, sem conteúdo, até o primeiro Publicar.`))) return;
      const { status, data } = await studio.api('/api/publish-site', { name, create, confirm: create });
      if (status !== 200) return studio.ui.toast(data?.message ?? `O link não foi cadastrado (erro ${status}).`, 'error');
      dialog.close();
      studio.ui.toast(`Link cadastrado: ${data.url}. Publicar já está na barra.`, 'ok');
      setTimeout(() => location.reload(), 900);
    });
    dialog.showModal();
    dialog.querySelector('#site-name').focus();
  }

  const list = Object.assign(document.createElement('div'), { className: 'jobs-list' });
  const drawer = studio.ui.addPanel({ id: 'jobs', title: 'Tarefas', side: 'bottom', element: list });
  drawer.hidden = true;
  const close = Object.assign(document.createElement('button'), { type: 'button', className: 'btn jobs-close', textContent: 'Fechar' });
  close.addEventListener('click', () => { drawer.hidden = true; });
  list.before(close);

  // a button is off while its job runs, and every one while a turn may be changing the deck (the server refuses then)
  const runs = new Set();
  let busy = false;
  const update = (name) => { buttons[name].disabled = busy || runs.has(name); };
  studio.on('status', (e) => { busy = e.busy; Object.keys(buttons).forEach(update); });

  async function start(name, body = {}) {
    runs.add(name);
    update(name);
    const { status, data } = await studio.api(`/api/jobs/${name}`, body);
    if (status === 202) return;
    runs.delete(name);
    update(name);
    studio.ui.toast(data?.message ?? `A tarefa não começou (erro ${status}).`, 'error');
  }

  // publishing goes out to the web: ask first, naming the site once the kit knows it
  async function publish() {
    const { url, paths = ['/'] } = (await studio.api('/api/jobs/site')).data ?? {};
    const where = url ? `em ${url}` : 'no Netlify';
    const both = paths.length > 1 ? ` As duas versões vão juntas: ${paths.join(' e ')}.` : '';
    if (await studio.ui.confirm(`Publicar o deck ${where}?${both} Quem abrir o link passa a ver esta versão.`)) start('publish', { confirm: true });
  }

  // one card per job name: a new run replaces the card of the previous one and opens the drawer
  const cards = new Map(); // name -> {id, article, state, log}
  function card(e) {
    const old = cards.get(e.name);
    if (old?.id === e.id) return old;
    const label = LABELS[e.name] ?? e.name;
    const article = Object.assign(document.createElement('article'), { className: 'job' });
    article.setAttribute('aria-label', label);
    const state = Object.assign(document.createElement('span'), { className: 'job-state' });
    state.setAttribute('role', 'status');
    const log = Object.assign(document.createElement('pre'), { className: 'job-log', tabIndex: 0 });
    log.setAttribute('role', 'log');
    log.setAttribute('aria-live', 'off'); // the state line announces the end; the lines themselves stay quiet
    log.setAttribute('aria-label', 'Log');
    const head = Object.assign(document.createElement('p'), { className: 'job-head' });
    head.append(Object.assign(document.createElement('b'), { textContent: label }), state);
    article.append(head, log);
    if (old) old.article.replaceWith(article);
    else list.append(article);
    drawer.hidden = false;
    const c = { id: e.id, article, state, log };
    cards.set(e.name, c);
    return c;
  }

  studio.on('job', (e) => {
    const c = card(e);
    c.article.dataset.state = e.state;
    if (buttons[e.name]) {
      if (e.state === 'running') runs.add(e.name);
      else runs.delete(e.name);
      update(e.name);
    }
    if (e.line != null) {
      c.log.append(`${e.line}\n`);
      c.log.scrollTop = c.log.scrollHeight;
    }
    c.state.textContent = e.state === 'running' ? 'rodando…' : `${e.state === 'ok' ? 'concluído em' : 'falhou após'} ${seconds(e.ms)}`;
    if (e.file) {
      const where = Object.assign(document.createElement('p'), { className: 'job-file' });
      where.append('PDF: ', Object.assign(document.createElement('code'), { textContent: e.file }));
      if (e.url) where.append(' ', Object.assign(document.createElement('a'), { href: e.url, target: '_blank', rel: 'noopener', textContent: 'Abrir' }));
      c.article.append(where);
    }
    c.article.lastElementChild.scrollIntoView({ block: 'nearest' }); // the drawer follows the job that moved
  });
}
