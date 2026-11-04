// Projetos: a top-bar button opens a panel with the projects (this studio's, the default kit, then the imported ones,
// newest first, each with Abrir) and the form that makes a new talk from a PDF. A project opens in a new tab, in a
// studio of its own. The tab opens blank at the click, so no popup blocker stops it, and goes to the studio when the
// server answers; a link "Abrir o projeto" stays in the panel for when the tab did not open.
const LIMIT = 100 * 1024 * 1024; // bytes, as the server takes
const FORMAT = { html: 'HTML', beamer: 'Beamer' };
const make = (tag, props = {}, ...children) => {
  const el = Object.assign(document.createElement(tag), props);
  el.append(...children);
  return el;
};
const svg = (markup, className = '') => make('span', { className: `proj-glyph ${className}`, innerHTML: markup });

// each format in miniature, as its template looks: the HTML deck's white slide with its highlighter, the Beamer
// deck's navy title bar and three-part footline
const GLYPH = {
  html: '<svg viewBox="0 0 64 36" aria-hidden="true"><rect x=".5" y=".5" width="63" height="35" rx="2" fill="#fcfcfd" stroke="#c5ccd5"/><rect x="7" y="7" width="30" height="4" rx="1" fill="#172031"/><rect x="7" y="17" width="34" height="2.5" rx="1" fill="#8b95a5"/><rect x="7" y="23" width="20" height="5" rx="1" fill="#ffd64a"/><rect x="7" y="24.2" width="16" height="2.5" rx="1" fill="#172031"/><rect x="45" y="15" width="12" height="14" rx="1" fill="#e3e6eb"/></svg>',
  beamer: '<svg viewBox="0 0 64 36" aria-hidden="true"><rect x=".5" y=".5" width="63" height="35" rx="2" fill="#ffffff" stroke="#c5ccd5"/><path d="M1 3a2 2 0 0 1 2-2h58a2 2 0 0 1 2 2v7H1z" fill="#0d3366"/><rect x="5" y="4.5" width="22" height="2.5" rx="1" fill="#ffffff"/><circle cx="8" cy="16" r="1.4" fill="#0d3366"/><rect x="11" y="15" width="26" height="2" rx="1" fill="#8b95a5"/><circle cx="8" cy="22" r="1.4" fill="#0d3366"/><rect x="11" y="21" width="20" height="2" rx="1" fill="#8b95a5"/><path d="M1 31h16v4H3a2 2 0 0 1-2-2z" fill="#668ca6"/><rect x="17" y="31" width="38" height="4" fill="#03506f"/><path d="M55 31h8v2a2 2 0 0 1-2 2h-6z" fill="#0d3366"/></svg>',
};
const ICON = '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><rect x="3" y="8" width="14" height="10" rx="1.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M7 4.5h12a2 2 0 0 1 2 2V14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
const CLOSE = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
const PDF_ICON = '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M6 2.75h8l4.25 4.25v14.25H6z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M14 2.75V7h4.25" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M12 10.5v6.5M9.25 14.25 12 17l2.75-2.75" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

const size = (bytes) => (bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB`
  : `${(bytes / 1024 / 1024).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} MB`);
const day = (iso) => new Date(iso).toLocaleDateString('pt-BR');
// the end of a path says the most: …\Deck Studio\Artigo (the whole path is the title)
const shortPath = (path) => {
  const parts = path.split(/[\\/]+/);
  return parts.length > 3 ? `…\\${parts.slice(-2).join('\\')}` : path;
};

// what the server refuses in a name (files.plain): separators, drives, streams, wildcards, a trailing dot or space
const NOT_PLAIN = /[<>:"/\\|?*\x00-\x1f]|[. ]$/;
const NAME_RULE = 'Dê um nome ao projeto, sem os caracteres / \\ : * ? " < > |.';
const WAIT = 'Esta aba vai para o projeto assim que o studio dele estiver pronto.';
const words = (text) => text.split(/\s+/).filter(Boolean).join(' ');
// the PDF's file name as the project's name: spaces for underscores, at most 60 characters, cut before a word
const nameOf = (file) => {
  const text = words(file.replace(/\.pdf$/i, '').replace(/_/g, ' '));
  const cut = text.length > 60 ? text.slice(0, 61).lastIndexOf(' ') : -1;
  return (text.length <= 60 ? text : cut > 0 ? text.slice(0, cut) : text.slice(0, 60)).replace(/[ .]+$/, '');
};
// the folder a name suggests, as the server makes it: without the characters LaTeX refuses in a path (% ~ $ { })
const folderOf = (name) => words(name.replace(/[%~${}]/g, '')).replace(/^[ .]+|[ .]+$/g, '') || 'Projeto';

// A blank tab, opened while the click still counts as the author's; it says what it waits for until it goes.
function blankTab(text) {
  const tab = window.open('', '_blank');
  if (!tab) return null;
  try {
    tab.document.title = 'Abrindo o projeto…';
    tab.document.documentElement.style.colorScheme = 'light dark'; // dark, as the studio, when the system is
    tab.document.body.append(make('p', {
      style: 'margin: 42vh auto 0; max-width: 34em; text-align: center; font: 15px/1.5 system-ui, sans-serif; opacity: .72',
    }));
    tab.opener = null; // the project's studio gets no handle on this page
  } catch { /* a blank tab still does */ }
  tell(tab, text);
  return tab;
}
function tell(tab, text) {
  try { tab.document.body.lastChild.textContent = text; } catch { /* closed, or gone to the project */ }
}

export default function projects(studio) {
  const button = make('button', { type: 'button', className: 'btn proj-button', innerHTML: `${ICON}<span>Projetos</span>` });
  button.title = 'Abrir outro projeto ou criar uma apresentação a partir de um PDF';
  document.getElementById('project').after(button);

  // ---------- the panel ----------
  const dialog = make('dialog', { className: 'projects' });
  dialog.setAttribute('aria-labelledby', 'projects-h');
  const close = make('button', { type: 'button', className: 'icon-btn', title: 'Fechar', innerHTML: CLOSE, onclick: () => dialog.close() });
  close.setAttribute('aria-label', 'Fechar');
  const head = make('header', { className: 'proj-head' }, make('h2', { id: 'projects-h', textContent: 'Projetos' }), close);

  const list = make('ul', { className: 'proj-list' });
  list.setAttribute('aria-label', 'Projetos');
  const listError = make('p', { className: 'proj-error', hidden: true });
  listError.setAttribute('role', 'alert');
  const listDone = make('p', { className: 'proj-done', hidden: true }); // the link, when the browser kept the tab shut
  listDone.setAttribute('role', 'status');
  const side = make('section', { className: 'proj-side' }, list, listError, listDone);
  side.setAttribute('aria-label', 'Abrir um projeto');

  // the form: PDF, Nome, Formato, Idioma dos slides, Pasta
  const form = make('form', { className: 'proj-new', noValidate: true });
  form.setAttribute('aria-labelledby', 'proj-new-h');
  const file = make('input', { type: 'file', accept: '.pdf,application/pdf', className: 'sr-only' });
  file.setAttribute('aria-labelledby', 'proj-pdf-l');
  const dropText = make('span', { className: 'proj-drop-text' });
  const drop = make('label', { className: 'proj-drop' }, file, svg(PDF_ICON, 'pdf'), dropText);
  // or a folder (its PDFs, notes, .tex/.bib and images, all of them into context/), or several files dropped at once
  const dir = make('input', { type: 'file', className: 'sr-only', multiple: true });
  dir.webkitdirectory = true;
  dir.setAttribute('aria-label', 'Escolher uma pasta');
  const pickDir = make('button', { type: 'button', className: 'btn proj-pick-dir', textContent: 'Ou escolha uma pasta' });
  pickDir.addEventListener('click', () => dir.click());
  const name = make('input', { id: 'proj-name', type: 'text', autocomplete: 'off', spellcheck: false, maxLength: 200 });
  const folder = make('input', { id: 'proj-folder', type: 'text', autocomplete: 'off', spellcheck: false, className: 'proj-path-input' });
  // what the PDF cannot say: the time of the talk, the audience, the event and its date, what to stress
  const notes = make('textarea', { id: 'proj-notes', rows: 3, maxLength: 1000,
    placeholder: 'Ex.: 20 minutos, para a banca da qualificação em 12/11. Destaque os resultados.' });
  const choice = (group, value, label, extra) => {
    const input = make('input', { type: 'radio', name: group, value, checked: value === 'html' || value === 'pt' });
    return make('label', { className: `proj-choice ${group}` }, input, ...(extra ? [extra] : []), make('span', { textContent: label }));
  };
  const formats = make('fieldset', { className: 'proj-formats' }, make('legend', { textContent: 'Formato' }),
    choice('format', 'html', 'HTML (deck web)', svg(GLYPH.html)), choice('format', 'beamer', 'Beamer (LaTeX)', svg(GLYPH.beamer)));
  const languages = make('fieldset', { className: 'proj-languages' }, make('legend', { textContent: 'Idioma dos slides' }),
    choice('language', 'pt', 'Português'), choice('language', 'en', 'English'));
  const formError = make('p', { className: 'proj-error', hidden: true });
  formError.setAttribute('role', 'alert');
  const STEPS = ['Extraindo o PDF…', 'Abrindo o projeto…'];
  const steps = make('ol', { className: 'proj-steps', hidden: true }, ...STEPS.map((text) => make('li', { textContent: text })));
  steps.setAttribute('aria-label', 'Andamento');
  const done = make('p', { className: 'proj-done', hidden: true });
  done.setAttribute('role', 'status');
  const create = make('button', { type: 'submit', className: 'btn primary', textContent: 'Criar apresentação' });
  // the fields scroll; the error, the steps, the status and the button stay below them, always in view
  form.append(
    make('div', { className: 'proj-fields' },
      make('h3', { id: 'proj-new-h', textContent: 'Nova apresentação a partir de um PDF ou de uma pasta' }),
      make('div', { className: 'proj-field' }, make('span', { id: 'proj-pdf-l', className: 'proj-label', textContent: 'PDF ou pasta' }), drop,
        dir, pickDir),
      make('div', { className: 'proj-field' }, make('label', { className: 'proj-label', htmlFor: name.id, textContent: 'Nome' }), name),
      formats, languages,
      make('div', { className: 'proj-field' }, make('label', { className: 'proj-label', htmlFor: folder.id, textContent: 'Pasta' }), folder),
      make('div', { className: 'proj-field' }, make('label', { className: 'proj-label', htmlFor: notes.id },
        'Instruções para o agente ', make('span', { className: 'proj-optional', textContent: '(opcional)' })), notes)),
    make('div', { className: 'proj-foot' }, formError, steps, done,
      make('div', { className: 'proj-actions' },
        make('p', { className: 'proj-hint', textContent: 'O agente começa logo em seguida, na aba do projeto, e leva alguns minutos.' }),
        create)));
  dialog.append(head, make('div', { className: 'proj-body' }, side, form));
  document.body.append(dialog);

  let pdf = null; // the chosen File
  let bundle = null; // or the chosen folder, or several files: [File]
  let base = ''; // where new projects go: <base>\<Nome> unless the author typed a folder
  let named = false; // the author typed the name
  let placed = false; // the author typed the folder
  let creating = null; // the name being imported
  const openLink = (url) => make('a', { href: url, target: '_blank', rel: 'noopener', textContent: 'Abrir o projeto' });

  // ---------- the list ----------
  async function refresh() {
    const { status, data } = await studio.api('/api/projects');
    if (status !== 200) return Object.assign(listError, { hidden: false, textContent: data?.message ?? `A lista de projetos não veio (erro ${status}).` });
    base = data.projectsFolder;
    autoFolder();
    // this studio's own deck first when the list does not have it (a kit opened by hand, as in the tests)
    const here = data.projects.some((p) => p.here) ? [] : [{ ...data.current, format: studio.project?.format, here: true }];
    list.replaceChildren(...[...here, ...data.projects].map(row));
    if (!data.projects.some((p) => !p.builtin)) {
      list.append(make('li', { className: 'proj-empty', textContent: 'Nenhuma apresentação criada de um PDF ainda. Comece pelo formulário ao lado.' }));
    }
  }

  function row(p) {
    const meta = make('span', { className: 'proj-meta' }, make('span', { className: 'proj-format', textContent: FORMAT[p.format] ?? p.format ?? 'HTML' }));
    if (p.created) meta.append(make('span', { textContent: `criado em ${day(p.created)}` }));
    if (p.running && !p.here) meta.append(make('span', { className: 'proj-live', textContent: 'aberto' }));
    if (p.missing) meta.append(make('span', { className: 'proj-gone', textContent: 'pasta não encontrada' }));
    const text = make('div', { className: 'proj-text' }, make('b', { className: 'proj-name', textContent: p.name }), meta,
      make('span', { className: 'proj-path', textContent: shortPath(p.path), title: p.path }));
    const li = make('li', { className: 'proj' }, svg(GLYPH[p.format] ?? GLYPH.html, 'small'), text);
    li.toggleAttribute('data-missing', !!p.missing);
    if (p.here) {
      li.dataset.here = '';
      li.append(make('span', { className: 'proj-here', textContent: 'Neste studio' }));
    } else {
      const abrir = make('button', { type: 'button', className: 'btn', textContent: 'Abrir', onclick: () => open(p, abrir) });
      abrir.setAttribute('aria-label', `Abrir ${p.name}`);
      li.append(make('div', { className: 'proj-buttons' }, abrir, ...(p.builtin ? [] : [removeButton(p)])));
    }
    return li;
  }

  // Remover: the project leaves the list; nothing on the disk changes
  function removeButton(p) {
    const remove = make('button', { type: 'button', className: 'btn proj-remove', textContent: 'Remover',
      title: 'Tirar da lista. A pasta e os arquivos ficam no disco.' });
    remove.setAttribute('aria-label', `Remover ${p.name} da lista`);
    remove.onclick = async () => {
      listError.hidden = listDone.hidden = true;
      if (!(await studio.ui.confirm(`Tirar ${p.name} da lista de projetos? Nada é apagado do disco.`))) return;
      const { status, data } = await studio.api('/api/projects/remove', { path: p.path });
      if (status !== 200) Object.assign(listError, { hidden: false, textContent: data?.message ?? `O projeto não saiu da lista (erro ${status}).` });
      refresh();
    };
    return remove;
  }

  // Abrir: the project's studio, started or already running, in a new tab
  async function open(p, abrir) {
    listError.hidden = listDone.hidden = true;
    const tab = blankTab(`Abrindo ${p.name}. ${WAIT}`);
    abrir.disabled = true;
    const { status, data } = await studio.api('/api/projects/open', { path: p.path });
    abrir.disabled = false;
    if (status !== 200) {
      tab?.close();
      refresh();
      return Object.assign(listError, { hidden: false, textContent: data?.message ?? `O projeto não abriu (erro ${status}).` });
    }
    if (tab) tab.location.href = data.url;
    else {
      listDone.replaceChildren(`O navegador não abriu a aba de ${p.name}. `, openLink(data.url));
      listDone.hidden = false;
    }
    refresh();
  }

  // ---------- the form ----------
  const showDrop = () => {
    const pdfs = bundle?.filter((f) => /\.pdf$/i.test(f.name)).length;
    dropText.replaceChildren(...(pdf
      ? [make('b', { textContent: pdf.name }), make('span', { textContent: `${size(pdf.size)}. Clique ou solte outro para trocar.` })]
      : bundle
        ? [make('b', { textContent: `${bundle.length} arquivos (${pdfs} PDF${pdfs === 1 ? '' : 's'})` }),
          make('span', { textContent: `${size(bundle.reduce((n, f) => n + f.size, 0))}. Vão todos para context/.` })]
        : [make('b', { textContent: 'Solte o PDF aqui' }), make('span', { textContent: 'ou clique para escolher. Até 100 MB.' })]));
    drop.toggleAttribute('data-chosen', !!(pdf || bundle));
  };
  // <base>\<Nome>, shown to its end, where the project's own name is
  const autoFolder = () => {
    if (!base) return;
    const into = base.replace(/[\\/]+$/, '');
    folder.placeholder = `${into}\\<nome do projeto>`;
    if (placed) return;
    folder.value = name.value.trim() ? `${into}\\${folderOf(name.value.trim())}` : '';
    folder.scrollLeft = folder.scrollWidth;
  };
  const lock = (on) => {
    for (const el of form.elements) el.disabled = on;
    form.toggleAttribute('aria-busy', on);
  };
  const fail = (box, message) => Object.assign(box, { hidden: !message, textContent: message ?? '' });

  function choose(f) {
    if (!f || creating) return;
    done.hidden = steps.hidden = true;
    if (!/\.pdf$/i.test(f.name)) return fail(formError, 'Escolha um arquivo .pdf.');
    if (f.size > LIMIT) return fail(formError, 'O PDF passa de 100 MB.');
    fail(formError, null);
    pdf = f;
    bundle = null;
    if (!named) name.value = nameOf(f.name);
    autoFolder();
    showDrop();
  }

  file.addEventListener('change', () => choose(file.files[0]));
  // a folder, or several files: the server keeps PDFs, .md, .txt, .tex, .bib, .csv, .json and images
  const KEPT = /\.(pdf|md|txt|tex|bib|csv|json|png|jpe?g|webp|svg|gif)$/i;
  function chooseMany(list) {
    if (creating) return;
    const files = [...list].filter((f) => KEPT.test(f.name));
    done.hidden = steps.hidden = true;
    if (!files.length) return fail(formError, 'Nenhum arquivo serve: use PDF, .md, .tex, .bib, .txt ou imagens.');
    if (files.reduce((n, f) => n + f.size, 0) > LIMIT) return fail(formError, 'Os arquivos passam de 100 MB juntos.');
    fail(formError, null);
    bundle = files;
    pdf = null;
    const top = files[0].webkitRelativePath?.split('/')[0];
    if (!named) name.value = top ? nameOf(top) : nameOf(files.find((f) => /\.pdf$/i.test(f.name))?.name ?? files[0].name);
    autoFolder();
    showDrop();
  }
  dir.addEventListener('change', () => chooseMany(dir.files));
  // a PDF dropped anywhere on the panel is taken (and never opened by the browser in place of the studio)
  dialog.addEventListener('dragover', (e) => {
    if (!e.dataTransfer?.types.includes('Files')) return;
    e.preventDefault();
    drop.dataset.over = '';
  });
  dialog.addEventListener('dragleave', (e) => { if (!dialog.contains(e.relatedTarget)) delete drop.dataset.over; });
  dialog.addEventListener('drop', (e) => {
    if (!e.dataTransfer?.files.length) return;
    e.preventDefault();
    delete drop.dataset.over;
    if (e.dataTransfer.files.length > 1) chooseMany(e.dataTransfer.files);
    else choose(e.dataTransfer.files[0]);
  });
  name.addEventListener('input', () => { named = !!name.value; autoFolder(); });
  folder.addEventListener('input', () => { placed = !!folder.value; autoFolder(); });

  let tab = null; // the blank tab of the import that runs, which shows its steps too
  function step(n) { // 1: extracting, 2: opening
    steps.hidden = false;
    [...steps.children].forEach((li, i) => { li.dataset.state = i + 1 < n ? 'done' : i + 1 === n ? 'active' : ''; });
    tell(tab, `${STEPS[n - 1]} ${WAIT}`);
  }
  studio.on('projects', (e) => { if (e.step === 'opening' && e.name === creating) step(2); });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (creating) return;
    done.hidden = true;
    const title = name.value.trim();
    // what the browser can check goes before the tab opens: a refusal then opens and shuts no tab
    const problem = !pdf && !bundle ? 'Escolha o PDF ou a pasta da apresentação.' : !title ? 'Dê um nome ao projeto.' : NOT_PLAIN.test(title) ? NAME_RULE : null;
    if (problem) return fail(formError, problem);
    fail(formError, null);
    tab = blankTab(`${STEPS[0]} ${WAIT}`);
    creating = title;
    const query = new URLSearchParams({ name: creating, format: form.elements.format.value, language: form.elements.language.value,
      folder: folder.value.trim(), notes: notes.value.trim() });
    lock(true);
    step(1);
    let reply;
    if (bundle) {
      const body = new FormData();
      for (const f of bundle) body.append('files', f, f.webkitRelativePath || f.name); // its path in the folder
      reply = await studio.api(`/api/projects/import-files?${query}`, body);
    } else {
      reply = await studio.api(`/api/projects/import?${query}`, pdf,
        { headers: { 'Content-Type': 'application/pdf', 'x-file-name': encodeURIComponent(pdf.name) } });
    }
    const { status, data } = reply;
    const opened = tab;
    creating = tab = null;
    lock(false);
    steps.hidden = true;
    refresh(); // a project that opened only in part (a 500) is in the list too
    if (status !== 201) {
      opened?.close();
      return fail(formError, data?.message ?? `O studio não criou o projeto (erro ${status}).`);
    }
    if (opened) opened.location.href = data.url;
    done.replaceChildren(opened ? 'Pronto: o projeto abriu em outra aba. ' : 'O navegador não abriu a aba do projeto. ',
      openLink(data.url), ...(data.warning ? [` ${data.warning}`] : []));
    done.hidden = false;
    pdf = bundle = null;
    file.value = dir.value = '';
    named = placed = false;
    name.value = notes.value = '';
    autoFolder();
    showDrop();
  });

  showDrop();
  button.addEventListener('click', () => {
    listError.hidden = listDone.hidden = true;
    refresh();
    dialog.showModal();
  });
}
