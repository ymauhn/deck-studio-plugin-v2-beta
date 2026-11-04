// Files pane: the folders of GET /api/files (slide sources, images, context/, skills), with part jumps,
// @references in the composer and image thumbnails; files dropped on the pane upload into context/.
const OPEN_FIRST = ['slides', 'context']; // root kinds shown open at the start (in a Beamer project, see `start`)
const LIMIT = 50 * 1024 * 1024; // the server's upload limit, checked here before sending
const IMAGE = /\.(png|jpe?g|gif|webp|svg)$/i; // the images GET /api/files/image serves

export default function (studio) {
  const pane = document.querySelector('.pane.files');
  const tree = Object.assign(document.createElement('div'), { className: 'tree' });
  const sending = Object.assign(document.createElement('p'), { className: 'sending' }); // upload progress
  sending.setAttribute('role', 'status');
  // the drop zone is also a file chooser, for the keyboard
  const drop = Object.assign(document.createElement('label'), { className: 'drop' });
  const chooser = Object.assign(document.createElement('input'), { type: 'file', multiple: true, className: 'sr-only' });
  drop.append(chooser, 'Solte aqui artigos, .md, PDFs e imagens');
  pane.append(tree, sending, drop);
  let open = null; // paths of the folders shown open
  let shown = new Set(); // the paths of the slides roots last listed
  // a Beamer project works in its deck's folder, not in the HTML template: that folder comes first and open, and its
  // main .tex (studio.project.beamerStart) is the current file
  const start = studio.project?.format === 'beamer' ? studio.project.beamerStart : null;
  const own = (root) => !!start?.startsWith(`${root.path}/`);

  async function list(dir) {
    const { status, data } = await studio.api(`/api/files?dir=${encodeURIComponent(dir)}`);
    return status === 200 ? data : [];
  }

  // a part file's first slide is the first section whose data-loc points into that file
  function jump(path) {
    const slides = [...studio.deck.win().document.querySelectorAll('#stage section.slide')];
    const k = slides.findIndex((s) => s.dataset.loc?.startsWith(`${path}:`));
    if (k >= 0) studio.deck.go(k + 1);
  }

  // the part file of the slide on screen is the current one (in a Beamer project, its deck's main .tex)
  function markPart() {
    const loc = start ? `${start}:` : studio.deck.win().document.querySelector('#stage section.slide.active')?.dataset.loc ?? '';
    for (const b of tree.querySelectorAll('.file')) {
      if (loc.startsWith(`${b.title}:`)) b.setAttribute('aria-current', 'true');
      else b.removeAttribute('aria-current');
    }
  }
  const watchDeck = () => studio.deck.win().document.addEventListener('deck:change', markPart);
  studio.deck.frame.addEventListener('load', () => {
    watchDeck();
    markPart();
  });
  watchDeck();

  // clicking a part file only jumps to its first slide and hands the deck the keys (so the arrows keep stepping);
  // Alt+click, or a click on any other file, drops its "@path" reference in the composer for a message
  function file(entry, root) {
    const li = document.createElement('li');
    const name = Object.assign(document.createElement('button'), { type: 'button', className: 'file', textContent: entry.name, title: entry.path });
    name.addEventListener('click', (e) => {
      if (root.kind === 'slides' && !e.altKey) {
        jump(entry.path);
        studio.deck.win().focus();
        return;
      }
      studio.composer.insert(`@${entry.path} `);
    });
    li.append(name);
    if (root.kind === 'context' && IMAGE.test(entry.name)) {
      const place = Object.assign(document.createElement('button'), { type: 'button', className: 'place', textContent: 'Pôr no slide' });
      place.addEventListener('click', () => placeImage(entry.path));
      li.prepend(Object.assign(document.createElement('img'), { className: 'thumb', alt: '', src: `/api/files/image?path=${encodeURIComponent(entry.path)}` }));
      li.append(place);
    }
    return li;
  }

  // the agent copies the image into the deck with its add_image tool and places it (near the picked boxes, if any)
  async function placeImage(path) {
    const { status, data } = await studio.chat.send(`Ponha a imagem @${path} no slide ${studio.deck.state().slide}. Use a ferramenta add_image.`);
    if (status !== 202) studio.ui.toast(data?.message ?? `O studio não aceitou o pedido (erro ${status}).`, 'error');
  }

  // a folder lists its entries when it opens
  function folder(entry, root) {
    const details = Object.assign(document.createElement('details'), { className: 'folder' });
    const summary = document.createElement('summary');
    summary.append(Object.assign(document.createElement('span'), { textContent: `${entry.name}/` }));
    if (entry.readOnly) summary.append(' ', Object.assign(document.createElement('small'), { className: 'tag', textContent: 'só leitura' }));
    details.append(summary);
    details.addEventListener('toggle', async () => {
      if (!details.open) return void open.delete(entry.path);
      open.add(entry.path);
      const ul = Object.assign(document.createElement('ul'), { className: 'entries' });
      ul.setAttribute('aria-label', entry.path);
      for (const e of await list(entry.path)) ul.append(e.dir ? folder(e, root) : file(e, root));
      if (!ul.children.length) ul.append(Object.assign(document.createElement('li'), { className: 'empty', textContent: 'vazia' }));
      details.querySelector(':scope > ul')?.remove();
      details.append(ul);
      markPart();
    });
    details.open = open.has(entry.path);
    return details;
  }

  async function refresh() {
    const roots = (await list('')).sort((a, b) => own(b) - own(a)); // stable: the rest keep the server's order
    if (open) {
      // the slides folder changed (the deck's other language, deck/src-pt): the new one opens as the old one was
      for (const r of roots) if (r.kind === 'slides' && !shown.has(r.path) && [...shown].some((p) => open.has(p))) open.add(r.path);
    }
    open ??= new Set(roots.filter((r) => (start ? own(r) || r.kind === 'context' : OPEN_FIRST.includes(r.kind))).map((r) => r.path));
    shown = new Set(roots.filter((r) => r.kind === 'slides').map((r) => r.path));
    tree.replaceChildren(...roots.map((r) => folder(r, r)));
  }

  // uploads go one by one into context/; the server never overwrites, it adds " (2)" and so on
  async function upload(files) {
    for (const [i, f] of files.entries()) {
      if (f.size > LIMIT) {
        studio.ui.toast(`${f.name} passa de 50 MB e não foi enviado.`, 'error');
        continue;
      }
      sending.replaceChildren(document.createElement('progress'), ` Enviando ${f.name} (${i + 1} de ${files.length})…`);
      const { status, data } = await studio.api('/api/files/upload', f, { headers: { 'x-file-name': encodeURIComponent(f.name) } });
      if (status === 201) studio.ui.toast(data.name === f.name ? `Salvo em ${data.path}` : `${f.name} já existia; salvo como ${data.path}`, 'ok');
      else studio.ui.toast(data?.message ?? `${f.name} não foi enviado (erro ${status}).`, 'error');
    }
    sending.replaceChildren();
    refresh();
  }

  pane.addEventListener('dragover', (e) => {
    if (!e.dataTransfer?.types.includes('Files')) return;
    e.preventDefault();
    pane.classList.add('dropping');
  });
  pane.addEventListener('dragleave', (e) => {
    if (!pane.contains(e.relatedTarget)) pane.classList.remove('dropping');
  });
  pane.addEventListener('drop', (e) => {
    if (!e.dataTransfer?.files.length) return;
    e.preventDefault();
    pane.classList.remove('dropping');
    upload([...e.dataTransfer.files]);
  });
  chooser.addEventListener('change', () => {
    upload([...chooser.files]);
    chooser.value = '';
  });

  studio.on('chat', (e) => e.kind === 'turn-end' && refresh()); // the agent may have made or changed files
  studio.on('deck-reload', refresh); // the deck changed language: its slides folder too
  refresh();
}
