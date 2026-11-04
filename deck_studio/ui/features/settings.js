// Settings: the model, the effort and the skills of new chats. A button in the chat head opens them in a dialog; "Salvar" keeps
// them in the studio, and the chats opened afterwards use them. Skills come in groups: the project, the user's own,
// one group per installed plugin, and the ones bundled with Claude Code.
const MODEL_LABEL = { opus: 'Opus', sonnet: 'Sonnet', haiku: 'Haiku' };
const EFFORT_LABEL = { '': 'Padrão do modelo', low: 'Baixo', medium: 'Médio', high: 'Alto', xhigh: 'Muito alto', max: 'Máximo' };
const GROUP = { project: 'Do projeto (.claude/skills)', user: 'Suas skills (~/.claude/skills)', bundled: 'Embutidas no Claude Code' };
const make = (tag, props = {}) => Object.assign(document.createElement(tag), props);

// one <details> per group, open when it is the project's or the user's, or has a skill on
function groups(skills) {
  const byGroup = new Map();
  for (const s of skills) {
    const key = s.source === 'plugin' ? `Plugin ${s.plugin}` : GROUP[s.source];
    if (!byGroup.has(key)) byGroup.set(key, []);
    byGroup.get(key).push(s);
  }
  return [...byGroup].map(([title, list]) => {
    const details = make('details', { className: 'skill-group' });
    details.open = ['project', 'user'].includes(list[0].source) || list.some((s) => s.on);
    details.append(make('summary', { textContent: `${title} (${list.length})` }));
    const items = make('ul', { className: 'skill-list' });
    for (const s of list) {
      const box = make('input', { type: 'checkbox', name: 'skill', value: s.name, checked: s.on });
      const label = make('label');
      label.append(box, ` ${s.name.split(':').pop()}`);
      const item = make('li');
      item.append(label);
      items.append(item);
    }
    details.append(items);
    return details;
  });
}

const ICON = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M4 7h9M17 7h3M4 17h3M11 17h9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="15" cy="7" r="2" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="9" cy="17" r="2" fill="none" stroke="currentColor" stroke-width="2"/></svg>';

export default function (studio) {
  const button = make('button', { type: 'button', className: 'icon-btn', title: 'Configurações', innerHTML: ICON });
  button.setAttribute('aria-label', 'Configurações');
  button.addEventListener('click', open);
  document.querySelector('.chat-tools').append(button);

  async function open() {
    const { status, data } = await studio.api('/api/settings');
    if (status !== 200) return studio.ui.toast(data?.message ?? `As configurações não vieram (erro ${status}).`, 'error');

    const dialog = make('dialog', { className: 'settings' });
    const heading = make('h2', { id: 'settings-h', textContent: 'Configurações' });
    dialog.setAttribute('aria-labelledby', heading.id);
    const model = make('select', { id: 'settings-model' });
    for (const m of data.models) model.append(make('option', { value: m, textContent: MODEL_LABEL[m] ?? m }));
    model.value = data.model;
    const modelRow = make('p', { className: 'settings-row' });
    modelRow.append(make('label', { htmlFor: model.id, textContent: 'Modelo dos chats novos' }), model);

    const effort = make('select', { id: 'settings-effort' });
    for (const e of data.efforts) effort.append(make('option', { value: e, textContent: EFFORT_LABEL[e] ?? e }));
    effort.value = data.effort;
    const effortRow = make('p', { className: 'settings-row' });
    effortRow.append(make('label', { htmlFor: effort.id, textContent: 'Esforço dos chats novos' }), effort);

    const skills = make('fieldset', { className: 'skills' });
    skills.append(make('legend', { textContent: 'Skills dos chats novos' }), ...groups(data.skills));

    const form = make('form', { method: 'dialog' });
    const cancel = make('button', { type: 'button', className: 'btn', textContent: 'Cancelar' });
    const save = make('button', { type: 'submit', className: 'btn primary', textContent: 'Salvar' });
    const actions = make('div', { className: 'settings-actions' });
    actions.append(cancel, save);
    form.append(modelRow, effortRow, skills, actions);
    dialog.append(heading, form);

    cancel.addEventListener('click', () => dialog.close());
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      save.disabled = true;
      const on = [...skills.querySelectorAll('input:checked')].map((b) => b.value);
      const reply = await studio.api('/api/settings', { model: model.value, effort: effort.value, skills: on });
      save.disabled = false;
      if (reply.status !== 200) {
        return studio.ui.toast(reply.data?.message ?? `O studio não salvou as configurações (erro ${reply.status}).`, 'error');
      }
      dialog.close();
      studio.ui.toast('Configurações salvas. Valem para os chats novos.', 'ok');
    });
    dialog.addEventListener('close', () => dialog.remove());
    document.body.append(dialog);
    dialog.showModal();
  }
}
