# Plano: abrir o Deck Studio no GitHub como plugin do Claude Code

Data: 04/11/2026. Status: **proposta; decisões do dono de 04/11 registradas nas seções d e e.** Este documento não muda código, não reescreve histórico e não publica nada. O repositório `ymauhn/deck-studio` continua privado.

Base: o plano aprovado pelo dono em 04/11 (Fase 2 = plugin do Claude Code distribuído por um marketplace no GitHub; cada colega usa a própria assinatura; o app atual, que roda o Agent SDK na assinatura do dono, **não** é distribuído), a pesquisa `deck-studio-codigo` da mesma rodada, e `docs/LICENCA-PROPOSTA.md` e `RELATORIO-23H.md` do branch `publicacao`.

Varreduras feitas em 04/11 neste worktree (`origin/main` em `fb7bb58`, mais todos os branches remotos: 18 commits ao todo) e, só leitura, no kit `nexusgo_deck_kit`. Nos achados abaixo cito `arquivo:linha` e não copio nome de terceiros.

---

## a) Limpeza do histórico antes de abrir

### O que a varredura achou

Comandos: `git rev-list --all | xargs git grep -nE <padrão>` (conteúdo de todos os commits), `git log --all --format='%an %ae %cn %ce'` (autoria) e `git log --all --format=%B` (mensagens). Os segredos já tinham sido varridos em 03/11 (`docs/LICENCA-PROPOSTA.md` do branch `publicacao`): nenhum achado.

| # | O que | Onde (HEAD de `main`, salvo indicação) | Desde o commit | Peso |
|---|---|---|---|---|
| 1 | **GIFs de demonstração com o slide de título da defesa**: nome do autor, do orientador e dos coorientadores, instituição e data da defesa, legíveis | `docs/gifs/1-esforco.gif`, `2-idioma.gif`, `3-autonomia.gif` (frames do meio; conferi o 2 e o 3) | `b1a33cf`, mesclado em `2b79650` | **Resolvido pela decisão do dono de 04/11** (seção d): o que eles mostram é o mesmo conteúdo que o template vai publicar, então deixam de ser problema de privacidade. Podem ir para o README do plugin |
| 2 | E-mail pessoal do autor dos commits | os 18 commits (autor; 14 também como committer, 4 com committer `GitHub`) | todos | Médio: fica visível em qualquer clone e na API do GitHub |
| 3 | Nome completo do dono | `docs/SPEC.md:4`; `tests/unit/test_beamer_engine.py:250` (sobrenome, num caso de teste do título do Beamer) | `b4ef7ee` | Baixo (é o autor), mas sai junto |
| 4 | Caminhos pessoais (`C:\Users\Yeonatan\…`, `OneDrive\Desktop\nexusgo_deck_kit`) | `deck_studio/__main__.py:29` (`DEFAULT_KIT`); `CLAUDE.md:6,20,55`; `README.md:12,78`; `docs/IMPORT.md:29,31`; `docs/PYTHON.md:47`; `docs/SPEC.md:126,134,138`; `tests/helpers/kit_copy.py:9`; `tests/unit/test_autonomy.py:9,10,42,50,57,66`; `tests/unit/test_generic_config.py:8`; `tests/unit/test_shell_policy.py:10,11,29,48,51,52,57,76,77`; `tests/unit/test_write_guard.py:7,8,50,137,143,144,149`. No histórico também: `.gitignore`, `RELATORIO-23H.md`, `docs/LICENCA-PROPOSTA.md` (branch `publicacao`) | `b4ef7ee` em diante | Baixo: revela o nome de usuário do Windows e a pasta do OneDrive |
| 5 | Nome e arquivos do projeto da dissertação (NEXUS-GO): o título do deck, `nexus-go-defense.*`, a publicação no Netlify | `deck_studio/config.py:20,27,32,46,72,80,84,89,166`; `deck_studio/config.py:23` (`publish_netlify.ps1`); `deck_studio/__main__.py:83`; e cerca de 30 arquivos de teste (`tests/unit/test_nexus_config.py`, `tests/e2e/*`, `tests/fixtures/build.orig.mjs`) | `b4ef7ee` | Baixo: o repositório `ymauhn/nexus-go` já é público (`docs/CONTEXT.md:33` do kit), mas amarra o app a uma pessoa |
| 6 | Branch `feat/gerador-v1`: cabeçalhos que citam o kit NEXUS-GO e "a regra do autor de 04/11" | `deck_studio/templates/project/deck/src/deck.css:1,117`; `fonts.css:2`; `qa/check_deck.py:1`; `qa/audit_numbers.py:1`; `qa/shoot.py:1`; `.claude/skills/criar-apresentacao/ESTILO.md:3` | `741b719`, `cce46ce` | Baixo. Os 12 `exemplos/*.html` **não** têm conteúdo da tese (grep por proteína, GO, ProtT5, números do corpus: nada) |
| 7 | Mensagens de commit | `v2-colegas` em 2 mensagens; linhas `Claude-Session:` com URLs de sessão | vários | Muito baixo |

Não achado: senhas, chaves, telefone, CPF; nomes de orientadores **em texto** (só nos GIFs); números, tabelas, figuras ou texto da dissertação; PDFs (o único PNG é `tests/fixtures/beamer/figures/dot.png`, um ponto de teste).

### Métodos possíveis

1. **Repositório novo para o plugin, com histórico próprio** (o `ymauhn/deck-studio` atual fica privado para sempre, como o "app do dono").
   - Prós: zero reescrita; o plugin é código novo de qualquer forma (sai o Agent SDK, sai o servidor de chat, ver c); o histórico público nasce limpo; o app que o dono usa na defesa não é tocado.
   - Contras: o histórico do que já foi feito não aparece no portfólio; o código reaproveitado (QA, Beamer, importação de PDF, editor) entra num commit inicial "importado de ymauhn/deck-studio".
2. **`git filter-repo` no repositório atual**, com `--invert-paths --path docs/gifs/` (tira os GIFs de todos os commits), `--replace-text substituicoes.txt` (por exemplo `C:\Users\Yeonatan\OneDrive\Desktop\nexusgo_deck_kit==>C:\caminho\do\kit` e `Yeonatan Mauhnoom==>o autor`) e `--mailmap` (e-mail para `ymauhn@users.noreply.github.com`).
   - Prós: guarda o histórico e as datas.
   - Contras: muda todos os hashes; o clone do dono em `C:/Users/Yeonatan/deck-studio`, os worktrees e os PRs #2 a #6 ficam apontando para commits que não existem mais; exige force push na `main` (fora do que o orquestrador pode fazer); o GitHub guarda as refs dos PRs antigos (`refs/pull/*`), que só o suporte apaga. E o código continua com o Agent SDK, que não deve ser distribuído.
3. **Commit único (squash) num branch órfão, no mesmo repositório**, depois de limpar o HEAD.
   - Prós: simples.
   - Contras: os mesmos problemas de refs antigas e de PRs do item 2, sem guardar o histórico.

**Recomendação: o método 1.** Ele resolve a limpeza de graça, porque o plugin é outra peça de software. Se o dono quiser também abrir o app atual (só para mostrar o código), use o método 2 numa **cópia espelho** (`git clone --mirror` para um repositório novo), nunca no repositório em uso, e só depois de 16/11.

Com a decisão de 04/11 (seção d), a reescrita deixa de ser necessária por causa dos GIFs; sobram o e-mail e os caminhos pessoais, que o método 1 já evita.

Antes de qualquer abertura, nos dois casos:
- `git config user.email ymauhn@users.noreply.github.com` no repositório novo (e ativar "Keep my email address private" no GitHub, decisão do dono);
- trocar `DEFAULT_KIT` e os caminhos dos testes por uma variável (`STUDIO_KIT`, que os testes já leem) ou por um kit de exemplo;
- rodar de novo a varredura desta seção no repositório novo e anexar o resultado ao PR de abertura.

---

## b) Licença AGPL-3.0 e o README de abertura

### Licença

Recomendo **AGPL-3.0-only** para o plugin, como em `docs/LICENCA-PROPOSTA.md` (branch `publicacao`): o PyMuPDF (`pymupdf==1.28.2`, `pyproject.toml:11`) é AGPL-3.0 ou licença comercial da Artifex, e a AGPL dispensa ressalvas. As outras dependências são MIT, BSD-3 ou Apache-2.0 e são compatíveis. Itens a cuidar:
- `LICENSE` com o texto oficial da FSF, sem alterações, e um cabeçalho SPDX (`# SPDX-License-Identifier: AGPL-3.0-only`) nos arquivos novos;
- `THIRD_PARTY.md`: Moveable (MIT, `deck_studio/ui/vendor/moveable.min.js`, manter o aviso no topo do arquivo); as fontes embutidas em `fonts.css` do branch `feat/gerador-v1` (Atkinson Hyperlegible Next, Bricolage Grotesque, IBM Plex Mono: todas SIL OFL 1.1, que pede o aviso de copyright e a licença junto da fonte);
- o template de demonstração (seção d) tem licença própria: o código do repositório `nexus-go` é MIT e os resultados são CC BY 4.0 (`source/nexus-go/LICENSE`, `LICENSE-DATA` no kit); o texto e as figuras da dissertação não têm licença declarada no kit; o dono liberou a publicação em 04/11 (seção d), e o template pode levar um aviso "© o autor, uso com atribuição", ou a licença que o dono escolher para o conteúdo.

### O que muda no README para abrir

O README atual é do app pessoal ("Editor local do deck da defesa NEXUS-GO", `README.md:3`; caminhos em `README.md:12,78`). O README do plugin teria estas seções:

1. **O que é** (3 linhas): um plugin do Claude Code que cria e edita apresentações (HTML e Beamer) a partir de um artigo, uma tese ou uma pasta, com QA de números e de layout e um editor visual local.
2. **Requisitos**: Claude Code instalado e logado **com a sua própria conta** (Pro ou acima, ou chave de API do Console); Python 3.12 via `uv`; Node; Chromium do Playwright; TeX opcional.
3. **Instalar** (Windows e Linux): os comandos da seção c.
4. **Primeiro deck em 5 minutos**: `/deck-studio:criar-apresentacao`, o briefing, o template de exemplo.
5. **Editor visual**: como abrir, selecionar uma caixa e pedir a mudança no próprio Claude Code.
6. **Privacidade**: os artigos e os decks ficam no seu computador; o plugin não envia nada a servidor próprio; o que vai para a Anthropic é o que o Claude Code envia na sua sessão, sob os termos da sua conta.
7. **Uso da assinatura (aviso)**: "Este plugin roda dentro do Claude Code oficial, sem modificação, e usa a conta com que **você** entrou nele. O autor do plugin não fornece, revende nem intermedeia acesso ao Claude. Os limites de uso são os do seu plano, sujeitos aos termos da Anthropic."
8. **Licença** (AGPL-3.0), **terceiros** e **como contribuir**.
9. **Não afiliado à Anthropic**: o nome "Claude Code" aparece só em texto descritivo ("um plugin para o Claude Code"), nunca como nome ou logo do produto.

### A política da Anthropic (conferida na web em 04/11/2026)

- **Agent SDK overview** (code.claude.com/docs/en/agent-sdk/overview), nota em destaque: "Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK. Use the API key authentication methods described in the Quickstart instead." É o que impede distribuir o app atual: ele roda o Agent SDK e exige o login de assinatura (`docs/SPEC.md:47,181`; `CLAUDE.md:43`; a própria SPEC já diz, em `docs/SPEC.md:268`, que distribuir exigiria chave de API).
- **Legal and compliance** (code.claude.com/docs/en/legal-and-compliance), seção "Authentication and credential use":
  - "OAuth authentication is intended exclusively for purchasers of Claude Free, Pro, Max, Ultra, Team, and Enterprise subscription plans and is designed to support ordinary use of Claude Code and other native Anthropic applications."
  - "Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, Max, or Ultra plan credentials on behalf of their users. Moreover, developers may not collect, store, or intermediate Claude.ai credentials or session tokens."
  - E o que sustenta a rota do plugin: "Nor does it prevent an end user from signing in to the unmodified Claude Code binary with their own Claude subscription".
  - Na mesma página, "Acceptable use": "Advertised usage limits for Pro, Max, and Ultra plans assume ordinary, individual usage of Claude Code and the Agent SDK." E, sobre marca: não usar os nomes ou logos de Claude Code ou Anthropic no nome do produto nem sugerir parceria.

Leitura para o plano: um plugin instalado pelo colega no Claude Code dele, logado na conta dele, é uso comum do Claude Code; o plugin não oferece login, não guarda credenciais e não roteia pedidos. O que o plugin **não** pode ter: código que chame o Agent SDK ou a API com credencial de outra pessoa, ou que leia o token de login do Claude Code. Isto é leitura minha dos textos, não parecer jurídico; em dúvida, a página indica "contact sales".

---

## c) O plugin do Claude Code

Documentação conferida em 04/11/2026: code.claude.com/docs/en/plugin-marketplaces ("Create a marketplace"), /plugins/components.md ("Add components to a plugin") e /plugins/host-marketplace.md ("Host and maintain a marketplace").

### Estrutura proposta (repositório novo `ymauhn/deck-studio-plugin`, público)

```text
deck-studio-plugin/                  marketplace e plugin no mesmo repositório
├── .claude-plugin/marketplace.json  {"name": "ymauhn-deck", "owner": {...}, "plugins": [{"name": "deck-studio", "source": "./plugins/deck-studio"}]}
├── plugins/deck-studio/
│   ├── .claude-plugin/plugin.json   {"name": "deck-studio", "version": "0.1.0", "description": ...}
│   ├── skills/
│   │   ├── criar-apresentacao/      SKILL.md em fases A–G, ESTILO.md, exemplos/ (12 tipos), templates de docs (Fase 1)
│   │   ├── editar-slide/            ler a seleção do editor e aplicar a mudança
│   │   ├── revisar-deck/            QA + juiz com rubrica (qa/RUBRICA.md)
│   │   └── exportar/                PDF, Beamer, zip do Overleaf, roteiro.md
│   ├── agents/juiz.md               subagente só leitura (tools: Read, Grep, Glob), dá nota por slide
│   ├── hooks/hooks.json             PreToolUse em Write|Edit: barra source/, data/ e os arquivos gerados (porte do write_guard)
│   ├── .mcp.json                    servidor "deck" (stdio, Python via uv)
│   ├── server/                      pyproject.toml + pacote deck_tools: importar PDF/pasta, build, screenshot, check, export, beamer, editor
│   └── templates/
│       ├── projeto-vazio/           o scaffold atual (deck/, beamer/, qa/, docs/)
│       └── exemplo-nexus-go/        o deck de demonstração (liberado pelo dono em 04/11, seção d)
└── LICENSE, README.md, THIRD_PARTY.md
```

Por que assim:
- **O agente é o próprio Claude Code** do colega. Saem do plugin: `deck_studio/agent/*` (Agent SDK), o chat da tela, o *auth gate*, o seletor de modelo e esforço, a autonomia (o Claude Code já tem permissões). Isso também resolve a política da Anthropic.
- **Ferramentas por MCP, não por `bin/`.** A doc diz que `bin/` vai para o `PATH` do Bash e do PowerShell fora do sandbox, mas "claude.ai and Cowork don't install a plugin that has a top-level `bin/` directory". O servidor MCP funciona igual no Windows e no Mac e dá nomes estáveis (`mcp__plugin_deck-studio_deck__build`) para regras de permissão e hooks. Declaração:
  `{"mcpServers": {"deck": {"command": "uv", "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/server", "python", "-m", "deck_tools"], "env": {"UV_PROJECT_ENVIRONMENT": "${CLAUDE_PLUGIN_DATA}/venv"}}}}`. O venv vai para `${CLAUDE_PLUGIN_DATA}`, que "survives updates"; `${CLAUDE_PLUGIN_ROOT}` muda a cada versão.
- **Editor visual local**: reaproveita `deck_studio/ui` (seleção, comentário, mover, edição no lugar) e um servidor HTTP mínimo em 127.0.0.1 com token, aberto pela ferramenta `abrir_editor`. Sem chat. Ao clicar numa caixa, o editor grava `.deck-studio/selecao.json` no projeto (seletor, arquivo:linha, texto, captura PNG); a ferramenta `ler_selecao` devolve isso ao Claude Code, e a skill `editar-slide` aplica a mudança. O editor recarrega o slide quando o arquivo muda (o *watch* que já existe).
- **Guarda de escrita**: um hook `PreToolUse` com `matcher: "Write|Edit"` que nega caminhos protegidos. É regra que tem de valer sempre, e a doc recomenda hook (não skill) para isso.
- **Versão**: `version` só no `plugin.json`, subindo a cada release (a doc avisa que, sem mudar a string, os usuários não recebem os commits novos).

### Instalador do app

Não há instalador separado: o "instalar" é o do Claude Code mais um passo de dependências.
1. `claude plugin marketplace add ymauhn/deck-studio-plugin` e `claude plugin install deck-studio@ymauhn-deck` (ou `/plugin …` dentro da sessão).
2. Na primeira sessão, um hook `SessionStart` roda `uv sync` (cria o venv em `${CLAUDE_PLUGIN_DATA}`) e `uv run playwright install chromium`, só quando o `pyproject.toml` mudou (o padrão `diff -q` da doc).
3. A skill `/deck-studio:verificar` (ou a ferramenta `diagnostico`) diz o que falta: `uv`, Node, Chromium, TeX, Perl, com o comando de instalação de cada um para o sistema do colega.

Repositório **público** (decidido em 04/11, seção d): o colega não precisa de convite nem de conta no GitHub para instalar. A doc diz que o Claude Code clona com o `git` da máquina, sem perguntar; sem chave SSH do GitHub, use `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1` (a doc recomenda deixar a variável nas instruções, porque a instalação por `/plugin` e as atualizações não caem sozinhas para HTTPS).

### Manual de instalação

**Windows 10/11**
1. Claude Code: instalador oficial (code.claude.com), depois `claude` e entrar com a **sua** conta.
2. Git for Windows (traz o Git Bash e o `perl` que o `latexmk` usa).
3. `uv`: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`; o `uv` baixa o Python 3.12 sozinho (`requires-python = ">=3.12,<3.13"`, `pyproject.toml:5`).
4. Node LTS (o build do deck é `node deck/build.mjs`): `winget install OpenJS.NodeJS.LTS`.
5. (Opcional; o repositório é público) GitHub CLI: `winget install GitHub.cli`.
6. Os dois comandos do plugin acima; abrir uma sessão nova; aceitar o passo de dependências (o download do Chromium: tamanho em medição).
7. Opcional, Beamer: MiKTeX (instalar pacotes "on the fly": sim) ou TeX Live.

**Linux (Ubuntu/Debian)**
1. Claude Code: instalador oficial (code.claude.com), depois `claude` e entrar com a **sua** conta.
2. `sudo apt update && sudo apt install -y git perl curl`.
3. `uv`: o instalador oficial de astral.sh/uv (script `install.sh`, pela linha que a página indica); o `uv` baixa o Python 3.12 sozinho.
4. Node: `sudo apt install -y nodejs npm` (a versão mínima do Node para o `deck/build.mjs` fica em medição; se a do apt for velha demais, o pacote LTS do NodeSource).
5. Os comandos do plugin; sessão nova; aceitar o passo de dependências. No Linux, o Chromium do Playwright também precisa das bibliotecas do sistema: `uv run playwright install --with-deps chromium` (pede `sudo`).
6. Opcional, Beamer: `sudo apt install -y texlive-latex-extra texlive-fonts-recommended latexmk biber` (a lista mínima de pacotes fica em medição no primeiro teste).

O Mac fica fora do piloto (decisão de 04/11: os colegas usam Linux ou Windows).

Teste de fumaça nos dois: `/deck-studio:verificar`, depois criar um deck a partir de um PDF de exemplo CC-BY, `build`, `check`, exportar PDF.

### O que no código só roda no Windows hoje (o porte mira o Linux) (grep neste worktree, `main` em `fb7bb58`)

| Onde | O quê | Conserto proposto |
|---|---|---|
| `deck_studio/__main__.py:13,14,19` | `import ctypes`, `import msvcrt`, `from ctypes import wintypes` no topo: o módulo nem importa no Linux (`msvcrt`) | importar dentro de um `if sys.platform == "win32"` |
| `deck_studio/__main__.py:50-59` | `watch_parent`: `ctypes.WinDLL("kernel32")`, `OpenProcess`, `WaitForSingleObject` | no POSIX, uma *thread* que testa `os.kill(pid, 0)` a cada segundo e sai no `ProcessLookupError` (`# ponytail:` 1 s de atraso, aceitável). No plugin, provavelmente some: não há *studio* filho por projeto |
| `deck_studio/__main__.py:70,73` | `os.O_BINARY` e `msvcrt.locking(fd, LK_NBLCK, 1)` (trava do diretório de dados) | `getattr(os, "O_BINARY", 0)`; uma função `lock_byte(fd, wait)` num módulo só, com `msvcrt.locking` no Windows e `fcntl.lockf(fd, LOCK_EX \| LOCK_NB, 1, 1 << 30)` no POSIX |
| `deck_studio/projects.py:16,120,122,127,181` | `import msvcrt`, `O_BINARY`, `msvcrt.locking(LK_LOCK)` / `LK_UNLCK` | a mesma `lock_byte` (com espera) e `getattr(os, "O_BINARY", 0)` |
| `deck_studio/beamer/engine.py:62`; `deck_studio/features/jobs.py:51`; `deck_studio/projects.py:169` | `taskkill /T /F /PID` para matar a árvore de processos | no POSIX, abrir o filho com `start_new_session=True` e matar com `os.killpg(os.getpgid(pid), signal.SIGKILL)`; uma função `kill_tree(proc)` usada nos três lugares |
| `deck_studio/beamer/engine.py:57`; `deck_studio/config.py:184`; `deck_studio/features/jobs.py:45`; `deck_studio/projects.py:204,265` | `creationflags=subprocess.CREATE_NO_WINDOW` (o atributo não existe fora do Windows: `AttributeError`) | constante `NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)` |
| `deck_studio/beamer/engine.py:119,176` (comentário em `:164`) | `-max-print-line=10000`, opção de linha de comando do MiKTeX; no TeX Live é variável do `texmf.cnf` | passar a opção só no MiKTeX (detectar por `pdflatex --version`) e, no TeX Live, pôr `max_print_line=10000` no `env` do processo (o kpathsea lê variáveis do `texmf.cnf` do ambiente; confirmar no primeiro Linux) |
| `deck_studio/beamer/engine.py:26-27,40` | `PERL_PLACES` com pastas do Git for Windows e do Strawberry Perl, e `perl.exe` | fora do Windows, só `shutil.which("perl")` (no Linux, o pacote `perl` do apt) |
| `deck_studio/__main__.py:29,30,37,42` | `DEFAULT_KIT` com caminho pessoal; dados em `%LOCALAPPDATA%` | sem kit padrão; dados em `${CLAUDE_PLUGIN_DATA}` (no plugin) ou, no app, `LOCALAPPDATA` no Windows e `${XDG_DATA_HOME:-~/.local/share}/deck-studio` no Linux |
| `deck_studio/features/projects.py:37,79` | exemplo `C:\Users\voce\…` e pasta padrão em `%USERPROFILE%\Deck Studio` | `Path.home() / "Deck Studio"` e o exemplo conforme o sistema |
| `deck_studio/config.py:23` | publicar com `powershell … publish_netlify.ps1` | é só do deck NEXUS-GO: fica fora do plugin |
| `deck_studio/core/shell_policy.py:12,36,71` | política de shell que lê caminhos no formato Windows (`/c/Users` = `C:\Users`, `.exe`) | sai no plugin (as permissões do Claude Code substituem); no app, só se o app for portado |
| `Abrir Deck Studio.cmd` | lançador `.cmd` com `.venv\Scripts\python.exe` | sai no plugin; no app, um `abrir.sh` para o Linux |
| `deck_studio/ui` / testes | testes com caminhos `C:\Users\…` (lista em a.4) | `tmp_path` e `STUDIO_KIT`, rodando em CI com matriz `windows-latest` e `ubuntu-latest` |

O total de mudanças é pequeno e concentrado em três funções (`lock_byte`, `kill_tree`, `NO_WINDOW`) mais o TeX. Esforço em medição.

---

## d) O deck NEXUS-GO como template pronto dentro do plugin

Ideia: o deck da defesa, na versão atual, vira `templates/exemplo-nexus-go/`, o exemplo "no nível do nosso" que o colega abre para ver o método funcionando.

> **Decisão do dono, 04/11/2026 (repassada pelo orquestrador):** o template com o deck NEXUS-GO **pode expor tudo**: nomes, orientadores e números da dissertação. O deck vai ser publicado de qualquer forma e mostra o uso real. Com isso, as perguntas sobre o que anonimizar, se a dissertação e os dados podem ir, as notas, os agradecimentos e os links ficam respondidas. Os GIFs de `docs/gifs` também deixam de ser problema de privacidade (seção a, item 1).

O inventário abaixo, lido no kit (só leitura) em 04/11, fica como registro do que o template leva:

### Pessoas, instituição, datas
- Nome do autor, do orientador e dos dois coorientadores, instituição, curso e data da defesa: `deck/src/slides/00-opening.html:6-8` e `deck/src-pt/slides/00-opening.html:6-8`; `beamer/slides.tex:10-12`; `beamer/nexus-go-defense.tex:14-15` (autor e data); `beamer/academico/nexus-go-academic.tex:19,35,47-52`; `beamer/v2-colegas-pt/nexus-go-v2-pt.tex:96-101`; `docs/FACTS.md:19-27` (§1 inteira); `docs/CONTEXT.md:5-11`.
- Agradecimentos com os financiadores (uma agência pública e um banco) e a instituição: `deck/src/slides/06-conclusions.html:107-109` (e `src-pt`); `beamer/slides.tex:1163-1165`; `beamer/academico/nexus-go-academic.tex:666-668`; `beamer/v2-colegas-pt/nexus-go-v2-pt.tex:895-920`.
- Logos da instituição: `beamer/v2-colegas/logos/logo-ic.png`, `logo-unicamp.pdf` (marca de terceiros; precisa de licença de uso ou sai).
- Publicações (uma publicada com DOI, outra aceita com data prevista) e coautores: `docs/FACTS.md:29-42`.
- Banca: **nenhum nome** de membro da banca no kit; só a palavra "banca"/"committee" nas notas (`06-conclusions.html:65,113`; `beamer/slides.tex:1134,1168`).

### Números e tabelas da dissertação
- `data/thesis_tables.json`: 34 tabelas extraídas do `.tex`; `data/numbering.json`: numeração de figuras e tabelas.
- `docs/FACTS.md:43-260`: corpus, rede STRING, constantes do método, resultados de validação e teste, cobertura, custo, conectividade e as respostas às questões de pesquisa.
- Todos os slides de resultados (`deck/src/slides/03-data.html` a `07-backup.html`, e a cópia em `src-pt`) e as tabelas do Beamer (`beamer/academico/tables.tex`, `beamer/v2-colegas/tables.tex`, `gains.tex`).

### Fonte, figuras e texto
- `source/thesis/dissertation.tex` (o texto inteiro da dissertação), 21 figuras PNG na raiz e 10 arquivos em `cap5/`; `source/nexus-go/` (clone do repositório público, MIT para o código e CC BY 4.0 para os resultados).
- As 24 figuras da tese mais 2 TikZ que o deck usa: lista em `docs/FIGURES.md:7-79`; cópias em `beamer/figures/` (23 arquivos) e nas pastas `figures/` das variantes Beamer.
- Notas do apresentador: blocos `<aside class="notes">` nos 8 arquivos de slide (56 linhas com o bloco, por `grep -c`, em `deck/src/slides/*.html`, e o mesmo em `src-pt`); `\note{…}` em `beamer/slides.tex`; o roteiro narrado `video/script.md` e os vídeos prontos `video/nexus-go-talk.mp4`, `video-pt/nexus-go-defesa-pt*.mp4` (com voz sintética).
- `docs/STORYLINE.md` (812 linhas, o roteiro slide a slide com as notas), `DECISIONS.md`, `PROMPT.md`, `TODO.md`.

### Links e caminhos pessoais
- Repositório do código: `docs/FACTS.md:28`, `docs/CONTEXT.md:33`, `06-conclusions.html:107`, `beamer/slides.tex:1163`.
- Site publicado no Netlify (com `noindex`): `DECISIONS.md:94,167`, `deck/tools/netlify-site.json:4`.
- Caminhos da máquina do dono, incluindo a pasta com o relatório de plágio e os resultados brutos: `docs/CONTEXT.md:24-33`.

### O que entra (decidido)
O deck HTML (EN e PT), o Beamer, os dados (`data/`, `docs/FACTS.md`), as figuras da tese e as notas do apresentador entram **como estão**, com nomes, orientadores, instituição, datas, números e tabelas, conforme a decisão acima.

Ficam fora porque não são conteúdo do deck, e não por privacidade:
- `docs/CONTEXT.md:24-33`, que guarda os caminhos da máquina do dono (incluindo a pasta do relatório de plágio e os resultados brutos); no template, o arquivo leva só o resto;
- os `.pdf`, `.zip`, `.log` e `.aux` gerados (o template os gera de novo) e a ferramenta do Netlify (`deck/tools/netlify-site.json`, `publish_netlify.ps1`), que publica no site e com a conta do dono;
- os vídeos `video/*.mp4` e `video-pt/*.mp4`, pelo tamanho. O roteiro `video/script.md` entra.

Duas observações, sem pedir decisão nova:
- **Logos** (`beamer/v2-colegas/logos/`) são marcas da instituição. Entram como no deck da defesa; se a instituição restringir o uso fora de trabalhos dela, eles saem numa versão seguinte.
- **Auditoria de números:** o `qa/audit_numbers.py` do exemplo confere contra `source/thesis/dissertation.tex`, que agora pode ir no template.

### Respostas do dono às perguntas abertas (04/11/2026, repassadas pelo orquestrador)

1. **Repositório do plugin: público desde já.** Quem cria `ymauhn/deck-studio-plugin` e o torna público é o orquestrador, depois da varredura da etapa 8 (caminhos pessoais, e-mail e segredos), feita antes do primeiro push público.
2. **Licença: AGPL-3.0.**
3. **Colegas e sistemas: Linux ou Windows, não Mac.** O porte POSIX mira o Linux, com CI em `ubuntu-latest`; o manual cobre Windows e Linux (Ubuntu/Debian, com `apt`); o Mac fica fora do piloto.

Não há perguntas abertas neste plano.

Recomendações que valem se o dono não disser o contrário: e-mail `ymauhn@users.noreply.github.com` nos commits do repositório novo, e o app atual (`ymauhn/deck-studio`) continua privado.

---

## e) Ordem de execução

Ordem decidida em 04/11 (repassada pelo orquestrador): primeiro a preparação do repositório e a Fase 1; depois o porte para Linux, a montagem do plugin e os templates; depois a varredura; só então o push público, feito pelo orquestrador.

| Ordem | Etapa | O quê | Quem | Espera |
|---|---|---|---|---|
| 1 | 3 | Preparar o repositório `ymauhn/deck-studio-plugin` **localmente**, ainda sem push: e-mail noreply, `LICENSE` AGPL-3.0 (decidida), README da seção b | orquestrador | — |
| 1 | Fase 1 | O gerador passa no aceite, em `feat/gerador-v1` | sessão do Deck Studio | aceite do dono; os ajustes da apresentação dele |
| 2 | 2 | Portar para Linux as funções da tabela da seção c (`lock_byte`, `kill_tree`, `NO_WINDOW`, TeX Live, perl), com testes e CI em `ubuntu-latest` e `windows-latest` | sessão de ticket | — (não muda o comportamento no Windows) |
| 2 | 4 | Montar o plugin: skills da Fase 1, servidor MCP `deck`, hook de guarda, agente juiz, editor visual sem chat, `claude plugin validate` verde | sessão de ticket | — |
| 2 | 5 | Templates: `projeto-vazio` e `exemplo-nexus-go`, este copiado do kit na versão final, com o conteúdo completo (decisão de 04/11) menos o que a seção d deixa de fora; os GIFs de `docs/gifs` podem ir para o README | sessão de ticket | o dono terminar os ajustes da apresentação |
| 3 | 8 | Varredura do repositório local antes do primeiro push público: caminhos pessoais (`C:\Users\…`, OneDrive), e-mail pessoal nos commits e segredos (`sk-ant-`, `ghp_`, `AKIA`, chaves privadas, tokens). Nomes e dados da tese estão liberados e não contam como achado | orquestrador | — |
| 4 | push | Criar `ymauhn/deck-studio-plugin` no GitHub como **público** e fazer o primeiro push, só com a varredura limpa | orquestrador | varredura da etapa 8 sem achados |
| 5 | 6 | Teste no Windows do dono e num Linux (Ubuntu/Debian; um colega ou uma VM) | dono e um colega | — |
| 5 | 7 | Mandar aos colegas o link do marketplace e o manual; formulário de feedback; nota de privacidade | dono | o formulário é criado pelo dono |

### O que espera o dono
- O aceite da Fase 1 e o fim dos ajustes da apresentação (o template copia a versão final).
- O formulário de feedback e a lista nominal dos colegas do piloto.
- Nada disso pede deploy nem gasto fora da assinatura.
