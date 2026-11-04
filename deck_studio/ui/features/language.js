// Deck language, in the deck bar of the HTML deck: an EN | PT switch between the two copies of the slides, and
// "Traduzir para …", which asks the agent in the current chat for the copy in the other language (a normal turn,
// with its diff and undo). The language on screen is the one the build, Exportar PDF and Publicar use.
export default async function language(studio) {
  const bar = document.querySelector('.deck-bar');
  const group = Object.assign(document.createElement('div'), { className: 'lang' });
  group.setAttribute('role', 'radiogroup');
  group.setAttribute('aria-label', 'Idioma do deck');
  const translate = Object.assign(document.createElement('button'), { type: 'button', className: 'btn' });
  bar.append(group, translate);

  let state = null;
  let busy = false;

  function draw() {
    group.replaceChildren(...state.languages.map((l) => {
      const b = Object.assign(document.createElement('button'), { type: 'button', textContent: l.code.toUpperCase() });
      b.setAttribute('role', 'radio');
      b.setAttribute('aria-label', l.label);
      b.setAttribute('aria-checked', String(l.code === state.active));
      b.disabled = busy || !l.available;
      b.title = l.available ? `Mostrar o deck em ${l.label.toLowerCase()}` : `Ainda não há a versão em ${l.label.toLowerCase()}`;
      b.addEventListener('click', () => choose(l.code));
      return b;
    }));
    const other = state.languages.find((l) => l.code !== state.active);
    translate.textContent = `Traduzir para ${other.label.toLowerCase()}`;
    translate.dataset.lang = other.code;
    translate.dataset.available = String(other.available);
    translate.disabled = busy;
  }

  async function load() {
    const { status, data } = await studio.api('/api/language');
    if (status === 200) {
      state = data;
      draw();
    }
  }

  async function choose(code) {
    if (code === state.active) return;
    const { status, data } = await studio.api('/api/language', { lang: code });
    if (status !== 200) return studio.ui.toast(data?.message ?? `O idioma não mudou (erro ${status}).`, 'error');
    state = data;
    draw();
  }

  translate.addEventListener('click', async () => {
    const { lang, available } = translate.dataset;
    const label = state.languages.find((l) => l.code === lang).label.toLowerCase();
    if (available === 'true' && !(await studio.ui.confirm(
      `Já existe a versão em ${label}. Traduzir de novo substitui essa versão, com as mudanças feitas nela.`))) return;
    const { data } = await studio.api(`/api/language/prompt/${lang}`);
    const reply = await studio.chat.send(data.text, { selection: [] });
    if (reply.status === 409) studio.ui.toast('Espere o pedido em andamento terminar para pedir a tradução.', 'error');
    else if (reply.status !== 202) studio.ui.toast(reply.data?.message ?? `O pedido não saiu (erro ${reply.status}).`, 'error');
  });

  // a turn may have written the other copy (the translation), and none runs while busy
  studio.on('status', (s) => {
    const was = busy;
    busy = !!s.busy;
    if (state && was !== busy) (busy ? draw() : load());
  });
  await load();
}
