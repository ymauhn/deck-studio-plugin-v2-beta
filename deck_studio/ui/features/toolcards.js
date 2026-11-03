// Tool cards: one compact card per tool call of the agent, with the file name, pattern or slide; never contents.
// The card appears with the call (`chat` event kind "tool", state "running") and takes its end state from the result.
const VERB = {
  Read: 'Leu', Edit: 'Editou', MultiEdit: 'Editou', NotebookEdit: 'Editou', Write: 'Escreveu',
  Glob: 'Listou', Grep: 'Buscou', Bash: 'Comando', PowerShell: 'Comando', WebFetch: 'Abriu', WebSearch: 'Pesquisou',
  Skill: 'Usou a skill', TodoWrite: 'Atualizou as tarefas',
  mcp__deck__get_selection: 'Leu a seleção', mcp__deck__screenshot_slide: 'Viu o slide',
  mcp__deck__check_slide: 'Conferiu o slide', mcp__deck__rebuild_deck: 'Recompilou o deck',
  mcp__deck__add_image: 'Adicionou a imagem', mcp__deck__compile_beamer: 'Compilou o Beamer',
  mcp__deck__screenshot_beamer_page: 'Viu uma página do Beamer',
};
const FILE_TOOLS = new Set(['Read', 'Edit', 'MultiEdit', 'NotebookEdit', 'Write']);
const ENDED = { denied: 'negado', error: 'erro', stopped: 'sem resultado' }; // stopped: the turn ended first

export default function (studio) {
  const cards = new Map(); // tool use id -> card

  function card(e) {
    const verb = VERB[e.name] ?? e.name.replace(/^mcp__[^_]+__/, '');
    const what = FILE_TOOLS.has(e.name) ? e.summary.split('/').pop() : e.summary;
    const el = Object.assign(document.createElement('article'), { className: 'tool-card' });
    el.setAttribute('aria-label', `Ferramenta: ${verb} ${what}`.trim());
    el.append(Object.assign(document.createElement('b'), { textContent: verb }));
    if (what) el.append(' ', Object.assign(document.createElement('code'), { textContent: what, title: e.summary }));
    return studio.chat.append(el, e.chatId);
  }

  studio.on('chat', (e) => {
    if (e.kind !== 'tool') return;
    if (!cards.has(e.id)) {
      if (!e.name) return; // the call was before this page opened
      cards.set(e.id, card(e));
    }
    const el = cards.get(e.id);
    el.dataset.state = e.state;
    if (ENDED[e.state]) el.append(' ', Object.assign(document.createElement('span'), { className: 'tool-detail', textContent: [ENDED[e.state], e.detail].filter(Boolean).join(': ') }));
  });
}
