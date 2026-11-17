---
name: instalar-studio
description: "Instala ou atualiza o app Deck Studio completo (o studio com chat dentro da página) neste computador, a partir do repositório privado ymauhn/deck-studio. Use quando o dono pedir para gerar, instalar, montar ou atualizar o Deck Studio, o studio com chat ou o app local num computador novo. Para o editor simples, sem chat, use a skill deck-studio:editar-slide."
---

# Instalar o Deck Studio com chat

O app é o Deck Studio do dono: o deck, o chat com o Claude, Desfazer, Beamer e Projetos, numa página local. O chat roda pelo Claude Agent SDK, com o login do Claude Code deste computador, ou seja, a assinatura de quem está logado aqui. O app apaga as variáveis `ANTHROPIC_*` ao abrir e nunca usa chave de API.

Ele vem do repositório **privado** `ymauhn/deck-studio`. É para o uso pessoal do dono, nos computadores dele. Se o clone falhar por falta de acesso (404, "Repository not found" ou 403), pare e diga, no idioma do autor: este app é pessoal do dono do repositório; o editor visual do plugin (`deck-studio:editar-slide`) faz a edição por clique sem o app.

## Passos

Fale com o autor no idioma em que ele escreve. Use caminhos entre aspas.

1. **Pasta:** `~/deck-studio` (no Windows, `C:\Users\<usuário>\deck-studio`), fora do OneDrive. Se o autor deu outra, use a dele.
2. **Programas:** confira `git --version` e `uv --version`. Se faltar algum, diga como instalar e pare:
   - Windows: Git for Windows (git-scm.com) e `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`;
   - Ubuntu ou Debian: `sudo apt install -y git curl` e o instalador oficial do `uv` (astral.sh/uv).
   - Opcionais, sem parar por eles: o Node, só para o kit NEXUS-GO; o TeX e o Perl, só para o Beamer. A skill `deck-studio:verificar` diz o que falta.
3. **Código:**
   - pasta nova: `git clone https://github.com/ymauhn/deck-studio.git "<pasta>"`. Se o Git pedir login no GitHub, o autor entra pela janela que abrir (ou por `gh auth login`); nunca peça a senha ou o token no chat;
   - pasta que já tem o app (`git -C "<pasta>" remote get-url origin` termina em `ymauhn/deck-studio.git`): `git -C "<pasta>" pull --ff-only`. Se houver mudanças locais e o pull recusar, mostre o `git status` e pergunte antes de qualquer outra coisa.
4. **Dependências**, dentro da pasta: `uv sync --frozen --no-dev`. O `uv` baixa o Python 3.12 sozinho.
5. **Chromium** das capturas e do PDF: `uv run --no-sync python -m playwright install chromium` (no Linux, `install --with-deps chromium`, que pede `sudo`).
6. **Login do chat:** o chat usa o login do Claude Code deste computador, e só aceita um login com assinatura. Se o autor está nesta sessão, em geral já está logado. Se o chat recusar ("Chat recusado: este login do Claude não tem uma assinatura"), o autor roda num terminal `claude auth login`; sem `claude` no PATH, o que vem com o SDK: `"<pasta>\.venv\Lib\site-packages\claude_agent_sdk\_bundled\claude.exe" auth login` (Linux: `<pasta>/.venv/lib/python3.12/site-packages/claude_agent_sdk/_bundled/claude auth login`).
7. **Abrir:** diga ao autor como abrir; não deixe o app preso a esta sessão.
   - Windows: dois cliques em `Abrir Deck Studio.cmd`, na pasta. Fechar a janela preta fecha o app.
   - Linux: `cd "<pasta>" && .venv/bin/python -m deck_studio`.
   - O navegador abre sozinho, numa página de `127.0.0.1` com um token.

## O deck que abre

- Sem `--kit`, o app abre o kit da defesa NEXUS-GO em `C:\Users\<usuário>\OneDrive\Desktop\nexusgo_deck_kit`. Se o OneDrive deste computador não tem essa pasta, o app abre do mesmo jeito; o autor usa o botão **Projetos** para criar uma apresentação a partir de um PDF ou abrir uma que já existe.
- Outro deck: `Abrir Deck Studio.cmd --kit "<pasta do deck>"` (ou o mesmo `--kit` no Linux).
- Os chats e o histórico ficam em `%LOCALAPPDATA%\deck-studio` (Linux: `~/.local/share/deck-studio`), um por computador. Eles não vêm do outro computador.

## No fim

Responda em três ou quatro linhas: a pasta, a versão (`git -C "<pasta>" log -1 --format=%h`), como abrir e o que faltou, se faltou algo.
