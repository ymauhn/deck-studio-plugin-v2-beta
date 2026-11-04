# Plano de execução das etapas 2, 4 e 5 do plugin (04/11/2026)

Detalha as etapas 2, 4 e 5 da [ordem de execução](plano-github-plugin.md#e-ordem-de-execução), agora que a Fase 1 está pronta (PR #16, [aceite](aceite/RELATORIO-ACEITE.md)). As decisões do dono continuam como em `plano-github-plugin.md`:
- repositório público `ymauhn/deck-studio-plugin`, criado pelo orquestrador depois da varredura da etapa 8;
- licença AGPL-3.0;
- Linux e Windows, sem Mac;
- o exemplo NEXUS-GO sem anonimizar.

Muda uma coisa: a liberação aos colegas não espera mais os ajustes do dono na apresentação dele. O template do exemplo copia o kit na versão do dia da etapa 5.

Cada etapa é um ticket próprio, com branch e PR. As referências de código abaixo foram conferidas em `feat/gerador-v1` (`e3eb5ef`).

## Etapa 2: o porte para Linux

**Objetivo:** o app e o servidor de ferramentas rodam no Ubuntu sem mudar o comportamento no Windows, com CI nos dois.

**Os três pontos de troca**, num módulo novo `deck_studio/core/plataforma.py`, com a versão Windows igual à de hoje:

| Função | Windows (hoje) | POSIX | Onde se usa |
|---|---|---|---|
| `lock_byte(fd, esperar)` e `unlock_byte(fd)` | `msvcrt.locking` | `fcntl.lockf(fd, LOCK_EX \| [LOCK_NB], 1, 1 << 30)` | `__main__.py:70,73`; `projects.py:16,123,125,130` |
| `kill_tree(proc)` | `taskkill /T /F /PID` | o filho aberto com `start_new_session=True`, e `os.killpg(os.getpgid(pid), SIGKILL)` | `beamer/engine.py:62`; `features/jobs.py:51`; `projects.py:181` |
| `NO_WINDOW` e `O_BINARY` | `subprocess.CREATE_NO_WINDOW`, `os.O_BINARY` | `0` (`getattr`) | `beamer/engine.py:57`; `config.py:196`; `features/jobs.py:45`; `projects.py:193,216,277`; `__main__.py:70` |

**O resto:**
- **`__main__.py:14,50`:** `msvcrt` e `ctypes.WinDLL` saem do topo e passam para dentro de `if sys.platform == "win32"`. O `watch_parent` no POSIX é uma thread com `os.kill(pid, 0)` a cada segundo (`# ponytail:` 1 s de atraso).
- **Pasta de dados:** `%LOCALAPPDATA%` no Windows e `${XDG_DATA_HOME:-~/.local/share}/deck-studio` no Linux (`__main__.py:30-42`). A pasta padrão dos projetos é `Path.home() / "Deck Studio"` (`features/projects.py:84`).
- **TeX** (`beamer/engine.py:119,164,176`):
  - `-max-print-line=10000` só no MiKTeX, detectado por `pdflatex --version`;
  - no TeX Live, `max_print_line=10000` no `env`;
  - `PERL_PLACES` (`:26`) só no Windows; fora dele, `shutil.which("perl")`.
- **`shell_policy`** lê caminhos do Git Bash (`/c/...`). No Linux, o caminho já é POSIX, e a função recebe um teste com `/home/...`.
- **Testes:** os que fixam `C:\Users\...` passam a usar `tmp_path`. Os que leem o kit real do dono (`STUDIO_KIT`) ficam marcados `kit` e pulam no CI.
- **CI** (`.github/workflows/ci.yml`):
  - matriz `ubuntu-latest` e `windows-latest`, Python 3.12 via `uv`;
  - `playwright install --with-deps chromium`;
  - `pytest -m "not kit and not live"`, só com o agente falso: o CI nunca chama a API;
  - TeX Live mínimo só no Ubuntu, para o teste do Beamer; a lista de pacotes fica em medição no primeiro run.

**Aceite:**
- o CI verde nos dois sistemas;
- no Windows, a suíte local com as mesmas falhas de hoje, sem nenhuma nova (as conhecidas leem o kit que o dono editou, issue #4);
- um projeto criado e um build no Ubuntu do CI.

**Esforço:** em medição. A mudança fica concentrada nas três funções e no TeX.

## Etapa 4: a montagem do plugin

**Objetivo:** `ymauhn/deck-studio-plugin` local, ainda sem push, com a estrutura da [seção c](plano-github-plugin.md#c-o-plugin-do-claude-code) e `claude plugin validate` verde.

**De onde vem cada peça:**

| Peça do plugin | Vem de | Muda o quê |
|---|---|---|
| `skills/criar-apresentacao/` (SKILL, ESTILO, 18 exemplos) | `templates/project/.claude/skills/criar-apresentacao/` | as ferramentas passam de `mcp__deck__*` para `mcp__plugin_deck-studio_deck__*`, e o juiz vira o subagente `juiz` |
| `skills/deck-*` (as 6 do método do dono) | `templates/project/.claude/skills/deck-*` | nada, além dos nomes das ferramentas |
| `skills/editar-slide/` | nova (curta) | lê `ler_selecao`, aplica a mudança, roda `check_slide` |
| `skills/revisar-deck/` | a fase E da criar-apresentacao | `run_qa` e o subagente juiz, até ficar verde |
| `skills/exportar/` | `features/jobs.py` (PDF) e `beamer/` | PDF, Beamer e o zip do Overleaf |
| `skills/verificar/` | nova | diz o que falta (uv, Node, Chromium, TeX, perl) e o comando de cada sistema |
| `agents/juiz.md` | `templates/project/.claude/agents/juiz-de-slides.md` e `qa/RUBRICA.md` | sai o `agent/judge.py`: o subagente do Claude Code já é uma sessão separada, só de leitura (tools: Read, Glob, Grep) |
| `.mcp.json` e `server/deck_tools/` (stdio, via `uv`) | `agent/tools.py`: `get_selection` (`ler_selecao`), `rebuild_deck`, `screenshot_slide`, `check_slide`, `add_image`, `compile_beamer`, `screenshot_beamer_page`, `run_qa` | os corpos das ferramentas ficam; sai o `create_sdk_mcp_server` em processo e entra um servidor stdio. Entram também `novo_projeto` (o `fill_template` com a importação de PDF ou pasta de `features/projects.py`), `exportar_pdf` e `abrir_editor` |
| `hooks/hooks.json` | `core/write_guard.py` | um `PreToolUse` em `Write\|Edit` que chama `write_guard.check(..., "deck")` e nega o que é protegido. O Bash fica com as permissões do Claude Code |
| editor visual, sem chat | `deck_studio/ui` com `features/edits.py`, `comments.py`, `drag.py` e `files.py` | um modo `--editor` do app, sem chat, autenticação, modelo, esforço, autonomia nem aprovações. O clique numa caixa grava `.deck-studio/selecao.json` |
| `templates/projeto-vazio/` | `templates/project/` | nada |
| `templates/exemplo-nexus-go/` | a etapa 5 | |

**Fica fora do plugin:**
- `agent/*` (o Agent SDK, o chat e a sessão) e `core/shell_policy.py`;
- `features/approvals.py`, `settings.py` (modelo, esforço, autonomia) e `publish_site.py` (Netlify, que fica para uma versão seguinte, com o login de cada colega);
- `Abrir Deck Studio.cmd`.

**Dependência nova:** o pacote `mcp`, o SDK Python oficial do Model Context Protocol, para o servidor stdio. Antes de adicioná-lo, o ticket roda a `nucleo:buscar-antes` e põe o bloco "Busca" no PR.

**Testes:**
- um teste de fumaça do servidor: sobe o stdio, lista as ferramentas, cria um projeto vazio, faz o build e roda `check_slide` e `run_qa`;
- o teste do hook, que nega `Write` em `deck/dist/` e deixa passar em `deck/src/slides/`;
- `claude plugin validate .` no CI.

**Aceite:**
- `claude plugin validate` verde e o CI verde;
- no Windows do dono, numa pasta nova:
  1. `claude plugin marketplace add <caminho local>` e `claude plugin install`;
  2. `/deck-studio:verificar`;
  3. um deck criado a partir de um PDF CC BY, com o QA 14 de 14 e o juiz sem bloqueantes;
  4. o editor abre, uma caixa selecionada chega ao Claude Code, e a mudança volta ao deck.

## Etapa 5: os templates

**`projeto-vazio`:** é o `templates/project/` da Fase 1 como está. Os componentes, as 7 skills, o QA e o juiz já estão nele, e o aceite já o testou.

**`exemplo-nexus-go`:** a cópia do kit na versão do dia, com o conteúdo completo (decisão de 04/11), menos o que a [seção d](plano-github-plugin.md#d-o-deck-nexus-go-como-template-pronto-dentro-do-plugin) deixa de fora:
- `docs/CONTEXT.md:24-33`, os caminhos da máquina;
- os `.pdf`, `.zip`, `.log` e `.aux` gerados;
- `deck/tools/netlify-site.json` e `publish_netlify.ps1`;
- `video/*.mp4` e `video-pt/*.mp4`.

Ele mantém o build dele: `node deck/build.mjs`, com o esbuild, e por isso o manual pede o Node. A auditoria `qa/run_all.py` roda contra `source/thesis/dissertation.tex`.

**Tamanho:** em medição. A leitura do kit no OneDrive passou de 2 min e foi para segundo plano; o número entra no PR da etapa. Se passar de algumas dezenas de MB, as figuras grandes vão como release asset, baixadas pelo `verificar`.

**Teste:** no CI, o exemplo builda (Node) e o `run_all.py` dele passa. Os testes que só valem na máquina do dono ficam marcados.

**Aceite:** o colega abre o exemplo, o deck abre igual ao da defesa (EN e PT), e o QA do kit passa.

## Ordem e dependências

1. **A etapa 2 primeiro**, porque o servidor do plugin herda as funções do porte.
2. **A etapa 4 depois da 2.** A parte de skills e agentes pode correr em paralelo, porque não depende do porte.
3. **A etapa 5 em paralelo com a 4**, já que só copia e testa.
4. **Ao fim da 4 e da 5,** a sessão avisa o orquestrador de que o conteúdo está pronto para a varredura da etapa 8.

## O que espera o dono

Nada novo. O teste num Linux (etapa 6) precisa de um colega ou de uma VM. O formulário de feedback e a lista do piloto (etapa 7) continuam com ele.
