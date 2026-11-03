# Deck Studio

Editor local de apresentações (HTML e Beamer) com o Claude num chat ao lado. Você clica numa caixa do slide, pede a mudança no chat e vê o slide mudar na hora. Cada mudança traz diff e **Desfazer**. O agente roda na sua assinatura do Claude, pelo Claude Agent SDK, e nunca usa chave de API.

Nasceu para o deck da defesa de mestrado NEXUS-GO e também cria uma apresentação nova a partir de um PDF (artigo, dissertação ou relatório).

> **Estado:** uso pessoal e só Windows por enquanto (usa `msvcrt`, `taskkill` e caminhos do Windows). **Licença:** ainda não escolhida; veja a proposta em [`docs/LICENCA-PROPOSTA.md`](docs/LICENCA-PROPOSTA.md).

## Requisitos e instalação

- Windows 10 ou 11, [uv](https://docs.astral.sh/uv/) e Python 3.12.
- O Claude Code com login feito numa assinatura (Pro ou Max). Ao abrir, o app apaga do próprio ambiente as variáveis `ANTHROPIC_*` e `CLAUDE*`.
- Node.js, quando o deck usa o build em Node do kit; uma distribuição TeX com `latexmk` (MiKTeX ou TeX Live) para a versão Beamer.

```powershell
git clone https://github.com/ymauhn/deck-studio
cd deck-studio
uv sync
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m deck_studio --kit "C:\caminho\do\seu\kit"
```

Sem `--kit`, o app abre o kit padrão do autor, definido em `deck_studio/__main__.py` (`DEFAULT_KIT`).

## Abrir

- Dê dois cliques em **`Abrir Deck Studio.cmd`**, nesta pasta, ou no atalho **Deck Studio** da área de trabalho.
- O navegador abre sozinho. Para fechar o app, feche a janela preta.
- Pelo terminal, nesta pasta: `.venv\Scripts\python.exe -m deck_studio`.
- Se o Deck Studio já estiver aberto, abrir de novo só mostra o endereço do que está rodando.

O app edita o kit em `C:\Users\Yeonatan\OneDrive\Desktop\nexusgo_deck_kit`. Para outro kit, use `--kit "<pasta>"`. Uma apresentação feita a partir de um PDF abre pelo botão **Projetos**; com `--kit` ela usa a própria pasta de dados, nunca a do NEXUS-GO.

## A tela

São três painéis: **Arquivos**, **Deck** e **Chat**.

### Deck

- As setas do teclado passam os slides e os passos.
- **Selecionar (S):** clique numa caixa para selecioná-la; Shift+clique junta mais caixas. Esc limpa a seleção.
- **Duplo clique num texto:** edita o texto ali mesmo. Enter salva, Esc cancela.
- **Comentar (C):** deixa uma nota numa caixa. As notas se juntam num lote, e você manda o lote para o chat de uma vez.
- **Mover (M):** arrasta e redimensiona a caixa selecionada no grid de 12 colunas.
- **Origem:** passe o mouse sobre um número para ver a linha da dissertação de onde ele vem.
- **HTML | Beamer:** troca para a versão Beamer.
  - Na versão acadêmica (`beamer/academico`), um clique num frame mostra a fonte LaTeX dele.
  - Para salvar a fonte, use Ctrl+S: o frame recompila.

### Chat

- A seleção vai junto com a mensagem, com uma imagem do slide.
- As respostas do agente aparecem formatadas, com negrito, listas e código.
- Cada pedido que muda arquivos ganha um cartão com **Ver diff** e **Desfazer**.
- **Parar** interrompe o pedido em andamento.
- **Abas:** cada aba é uma conversa separada, que continua depois de fechar o app. **Novo chat** abre outra, e F2 renomeia a aba.
- **Modelo:** Opus é o padrão; Sonnet e Haiku também estão disponíveis.
- **Configurações:** o modelo e as skills dos chats novos.
- **Aprovações:** comandos de terminal, acesso à web, scripts do deck e arquivos fora do deck esperam o seu **Permitir** ou **Negar**. O cartão mostra o pedido inteiro, com todas as linhas.
- **Erros:** se o agente parar no meio de um pedido, o chat diz o que houve e o que fazer, em geral mandar a mensagem de novo. O texto técnico fica dobrado em **Detalhe técnico**, e uma ferramenta que ficou sem resposta aparece em cinza, com "sem resultado".

### Arquivos

- Mostra as pastas que o agente usa: os slides, as imagens, `context/` e as skills.
- Arraste artigos, notas e imagens para `context/`, para o agente consultar.

### Tarefas

- **Exportar PDF:** gera o PDF do deck.
- **Publicar:** atualiza o site no Netlify.
- **Regenerar Beamer:** gera de novo a versão Beamer a partir do deck.
- Nenhuma tarefa roda enquanto o agente está mudando o deck.

## Criar uma apresentação a partir de um PDF

1. Clique em **Projetos**, na barra de cima.
2. Em **Nova apresentação a partir de um PDF**, solte o PDF na caixa ou clique nela para escolher. Vale um artigo, uma dissertação ou um relatório, de até 100 MB.
3. Confira os campos:
   - **Nome:** vem do nome do arquivo e vira o título do projeto.
   - **Formato:** **HTML (deck web)** ou **Beamer (LaTeX)**.
   - **Idioma dos slides:** português ou inglês. O agente fala com você sempre em português.
   - **Pasta:** por padrão `C:\Users\Yeonatan\Deck Studio\<Nome>`. Pode ser outra pasta nova ou vazia, fora do kit, com até 150 caracteres e sem `% ~ $ { }`.
   - **Instruções para o agente** (opcional): o que o PDF não diz, como a duração da fala, o público, o evento, a data e o que destacar.
4. Clique em **Criar apresentação**. Uma aba nova abre com o projeto, e o agente começa a montar os slides ali. Leva alguns minutos; acompanhe pelo chat e pelo deck.

Depois:

- **Editar:** como no deck da defesa, com seleção, chat, edição no lugar e **Desfazer**.
- **HTML:** **Exportar PDF** grava `deck/dist/deck.pdf`, na pasta do projeto.
- **Beamer:** o projeto abre na versão Beamer, com a pasta `beamer/apresentacao` aberta em **Arquivos**, e recompila a cada mudança no `.tex`. **Abrir PDF** mostra o PDF da última compilação, e **Exportar para Overleaf** grava um `.zip` em `exports/` e mostra o caminho completo dele no registro da tarefa.
- **Autor, instituição e evento:** o que nem o PDF nem as suas instruções dizem fica marcado nos slides, como `[autor]`, `[instituição]` e `[evento e data]`, para você preencher. O agente avisa no resumo.
- **Voltar a um projeto:** **Projetos**, depois **Abrir**. Cada projeto roda num studio próprio, na sua aba, e fecha junto com o Deck Studio. **Remover** só tira o projeto da lista; nada sai do disco.
- **Arquivos do projeto:** o PDF fica em `context/`, e o texto e as figuras extraídos dele, numa pasta com o nome do projeto dentro de `context/`.
- **PDF escaneado:** sem texto para extrair, o projeto é criado assim mesmo, com um aviso no painel, e o agente lê as páginas como imagens, o que demora mais.
- **O agente no projeto:** edita sozinho os slides, `context/`, as skills e `beamer/`; pede a sua aprovação para o código do deck, as ferramentas e o `CLAUDE.md`; e nunca mexe em `studio.json`, nos arquivos gerados e em `exports/`.

## O que o agente pode e não pode fazer

- **Livre:** editar os slides, o CSS, as imagens, `context/`, as skills do projeto e a versão acadêmica do Beamer.
- **Com a sua aprovação:** comandos de terminal, a web, o código do deck (`deck/src/**/*.js` e `shell.html`) e arquivos fora do kit.
- **Nunca:** a dissertação (`source/`), `data/` e os arquivos gerados (`deck/dist`, `deck/build`, `beamer/slides.tex`).
- **Scripts nos slides:** o deck aparece no app com uma política que bloqueia qualquer script escrito num slide. Assim, nada que o agente escreva num slide consegue aprovar pedidos nem publicar.
- **Desfazer:** cobre todas as mudanças feitas por arquivo, mas não o que um comando de terminal mudar.

## Para quem mexe no código

- **Pilha:** Python 3.12 (FastAPI, uvicorn e o Claude Agent SDK) e uma tela em HTML, CSS e JS puros.
- **Regras e especificações:** as regras estão no `CLAUDE.md`. A especificação está em `docs/SPEC.md`, com as decisões e contratos de Python em `docs/PYTHON.md`.
- **Testes:** `.venv\Scripts\python.exe -m pytest`, cerca de 390 testes em uns 18 minutos. Eles sempre rodam em cópias do kit.
- **Teste com o SDK real:** consome um pouco da assinatura. Rode `$env:STUDIO_LIVE=1; .venv\Scripts\python.exe -m pytest tests/live -s`.
- **Dados do app:** chats, histórico e compilações do Beamer ficam em `%LOCALAPPDATA%\deck-studio`.
