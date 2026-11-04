# Deck Studio

Editor local do deck da defesa NEXUS-GO, com o Claude num chat ao lado. Você clica numa caixa do slide, pede a mudança no chat e vê o slide mudar na hora. O agente roda na sua assinatura do Claude (Max), pelo Claude Agent SDK, e nunca usa chave de API.

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
- **Seguir o agente** (ligado por padrão): enquanto o agente edita, o deck vai sozinho para o slide de cada escrita, no último passo, e a caixa alterada pisca. O botão desliga e liga, e a escolha fica. Se você navegar à mão durante um pedido, ele pausa até o próximo pedido.
- **HTML | Beamer:** troca para a versão Beamer.
  - Na versão acadêmica (`beamer/academico`), um clique num frame mostra a fonte LaTeX dele.
  - Para salvar a fonte, use Ctrl+S: o frame recompila.
  - A compilação usa o `latexmk`, que precisa do Perl. O app procura um no PATH, no Git for Windows e no Strawberry Perl. Sem nenhum, compila com `pdflatex`, `bibtex` ou `biber` e o `pdflatex` mais duas vezes, e um erro diz o que instalar.
- **Idioma (EN | PT):** alterna o deck entre a versão em inglês e a em português.
  - **No deck da defesa,** o português é a árvore `deck/src-pt` do kit (`node deck/build.mjs --pt`). Com **PT**, o app mostra, seleciona e edita os arquivos de `deck/src-pt`, e **Arquivos** lista `deck/src-pt/slides`. **Exportar PDF** grava `deck/dist/nexus-go-defesa-pt.pdf`, e **Publicar** atualiza as duas versões do site.
  - **Num deck sem a versão em português,** **Traduzir para …** pede ao agente, no chat, a cópia em `deck/src/i18n/<idioma>/`. É um pedido como os outros, com **Ver diff** e **Desfazer**, e a chave passa a trocar entre as cópias.
  - A versão na tela é a que o build, **Exportar PDF** e **Publicar** usam, e a escolha continua depois de fechar o app.
  - Não dá para trocar o idioma durante um pedido.

### Chat

- A seleção vai junto com a mensagem, com uma imagem do slide.
- As respostas do agente aparecem formatadas, com negrito, listas e código.
- Cada pedido que muda arquivos ganha um cartão com **Ver diff** e **Desfazer**.
- **Parar** interrompe o pedido em andamento.
- **Abas:** cada aba é uma conversa separada, que continua depois de fechar o app. **Novo chat** abre outra, e F2 renomeia a aba.
- **Modelo:** Opus é o padrão; Sonnet e Haiku também estão disponíveis.
- **Esforço:** ao lado do modelo, de baixo a máximo, ou o padrão do modelo. Vale por chat; trocar no meio da conversa reconecta o agente no próximo pedido, na mesma conversa.
- **Configurações:** o modelo, o esforço e as skills dos chats novos.
- **Autonomia:** a chave acima da caixa de mensagem vale para todos os chats, a partir da próxima ação do agente.
  - **Perguntar sempre:** toda escrita, comando e acesso à web espera o seu **Permitir**.
  - **Editar o deck** (o padrão): edita os arquivos do deck sem perguntar. Comandos, web e os scripts do deck pedem aprovação.
  - **Autônomo:** também lê fora do deck e roda, sem perguntar, os comandos do próprio deck e os de leitura.
    - Do deck: o build (`node deck/build.mjs`, com ou sem `--pt`), o QA (`qa/*.py`), o `export_pdf.py`, o build do Beamer e o TeX (`pdflatex`, `bibtex`, `latexmk -norc`).
    - De leitura: `ls`, `cat`, `grep`, `diff`, `sed -n` e afins.
    - Ainda pedem: um comando que grava num arquivo (`>`, heredoc, `cp`, `mv`, `python -c`), um script que não é do deck e qualquer comando fora dessas listas.
  - **Em qualquer nível:** a escrita fora do deck continua barrada; a dissertação e os arquivos gerados continuam protegidos; e o código que o studio roda (os `.js` do deck, o build, as ferramentas, os scripts de QA, as configurações do Claude) pede aprovação. Publicar, a rede (incluindo a busca na web) e o `git push` também pedem.
- **Aprovações:** o que o nível de autonomia não libera espera o seu **Permitir** ou **Negar**. O cartão mostra o pedido inteiro, com todas as linhas.
- **Erros:** se o agente parar no meio de um pedido, o chat diz o que houve e o que fazer, em geral mandar a mensagem de novo. O texto técnico fica dobrado em **Detalhe técnico**, e uma ferramenta que ficou sem resposta aparece em cinza, com "sem resultado".

### Arquivos

- Mostra as pastas que o agente usa: os slides, as imagens, `context/` e as skills.
- Arraste artigos, notas e imagens para `context/`, para o agente consultar.

### Tarefas

- **Exportar PDF:** gera o PDF do deck.
- **Publicar:** atualiza o site no Netlify.
- **Regenerar Beamer:** gera de novo a versão Beamer a partir do deck.
- Nenhuma tarefa roda enquanto o agente está mudando o deck.

## Criar uma apresentação a partir de um PDF ou de uma pasta

1. Clique em **Projetos**, na barra de cima.
2. Em **Nova apresentação a partir de um PDF ou de uma pasta**, solte o PDF na caixa ou clique nela para escolher. Vale um artigo, uma dissertação ou um relatório, de até 100 MB.
   - **Ou escolha uma pasta** (ou solte vários arquivos de uma vez): PDFs, notas `.md`/`.txt`, `.tex`/`.bib`, `.csv` e imagens, até 100 MB juntos. Tudo vai para `context/`, e cada PDF é extraído numa pasta própria. O nome do projeto vem do nome da pasta, e o que não serve (um `.exe`, por exemplo) fica de fora, com aviso ao agente.
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
- **Publicar um projeto:** **Cadastrar link de publicação** liga o projeto a um site do Netlify, um que já existe na sua conta ou um novo com o nome que você der. O login é o da Netlify CLI desta máquina (`npx netlify login`). Depois, **Publicar** aparece na barra, com a mesma confirmação do deck da defesa, e o site sai com noindex. O link fica em `deck/tools/netlify-site.json`.
- **Beamer:** o projeto abre na versão Beamer, com a pasta `beamer/apresentacao` aberta em **Arquivos**, e recompila a cada mudança no `.tex`. **Abrir PDF** mostra o PDF da última compilação, e **Exportar para Overleaf** grava um `.zip` em `exports/` e mostra o caminho completo dele no registro da tarefa.
- **Autor, instituição e evento:** o que nem o PDF nem as suas instruções dizem fica marcado nos slides, como `[autor]`, `[instituição]` e `[evento e data]`, para você preencher. O agente avisa no resumo.
- **Voltar a um projeto:** **Projetos**, depois **Abrir**. Cada projeto roda num studio próprio, na sua aba, e fecha junto com o Deck Studio. **Remover** só tira o projeto da lista; nada sai do disco.
- **Arquivos do projeto:** o PDF fica em `context/`, e o texto e as figuras extraídos dele, numa pasta com o nome do projeto dentro de `context/`.
- **PDF escaneado:** sem texto para extrair, o projeto é criado assim mesmo, com um aviso no painel, e o agente lê as páginas como imagens, o que demora mais.
- **O agente no projeto:** edita sozinho os slides, `context/`, as skills e `beamer/`; pede a sua aprovação para o código do deck, as ferramentas e o `CLAUDE.md`; e nunca mexe em `studio.json`, nos arquivos gerados e em `exports/`.

## O que o agente pode e não pode fazer

- **Livre:** editar os slides, o CSS, as imagens, `context/`, as skills do projeto e a versão acadêmica do Beamer; no nível **Editar o deck** (o padrão), também os outros arquivos do deck que não são protegidos.
- **Com a sua aprovação:** o código do deck (`deck/src/**/*.js` e `shell.html`) e os arquivos fora do kit, em qualquer nível. Comandos de terminal e a web pedem aprovação, salvo os comandos locais e a consulta à web no nível **Autônomo**.
- **Nunca:** a dissertação (`source/`), `data/` e os arquivos gerados (`deck/dist`, `deck/build`, `beamer/slides.tex`).
- **Scripts nos slides:** o deck aparece no app com uma política que bloqueia qualquer script escrito num slide. Assim, nada que o agente escreva num slide consegue aprovar pedidos nem publicar.
- **Desfazer:** cobre todas as mudanças feitas por arquivo, mas não o que um comando de terminal mudar.

## Para quem mexe no código

- **Pilha:** Python 3.12 (FastAPI, uvicorn e o Claude Agent SDK) e uma tela em HTML, CSS e JS puros.
- **Regras e especificações:** as regras estão no `CLAUDE.md`. A especificação está em `docs/SPEC.md`, com as decisões e contratos de Python em `docs/PYTHON.md`.
- **Testes:** `.venv\Scripts\python.exe -m pytest`, cerca de 390 testes em uns 18 minutos. Eles sempre rodam em cópias do kit.
- **Teste com o SDK real:** consome um pouco da assinatura. Rode `$env:STUDIO_LIVE=1; .venv\Scripts\python.exe -m pytest tests/live -s`.
- **Dados do app:** chats, histórico e compilações do Beamer ficam em `%LOCALAPPDATA%\deck-studio`.
