# Teste de ponta a ponta gravado (item 3 da fila de 04/11/2026)

O dono ainda não tinha criado um projeto novo. Este teste fez esse caminho por ele, com o agente real, e gravou tudo.

## Resultado

O fluxo inteiro funcionou, e a publicação real está no ar: https://deck-studio-teste-e2e-0411.netlify.app. Ela tem só conteúdo mock, com noindex, e foi publicada pelo orquestrador com o login da Netlify CLI, como o dono autorizou.

| Passo | Como foi |
|---|---|
| Criar o projeto de uma pasta | A pasta mock entrou pelo "Ou escolha uma pasta" do painel Projetos: 2 PDFs arXiv CC BY 4.0, 2 notas `.md`, 2 imagens CC0 e as licenças. Cada PDF foi extraído numa pasta própria. |
| O agente gera o deck | O Claude Opus, pela assinatura, fez 10 slides e 1 de reserva em cerca de 2 min 16 s, segundo as notas e o "pedido do orientador" (no máximo 8 de conteúdo, um item por passo, a pergunta no fim). |
| Ir para o slide | "3" e "B1" levaram ao slide certo, e o total mostra "de 10 + 1 de reserva". |
| Editar pelo chat | A caixa do título do slide 3, selecionada e pedida em português, foi encurtada pelo agente, com Desfazer e Ver diff. |
| Seguir o agente | Com o deck no slide 1, o agente editou o 3, e o deck foi sozinho ao 3. |
| Edição direta | O duplo clique, o texto e Enter gravaram no arquivo. Na tomada original, o texto entrou no meio da frase (achado 4); a tomada nova, depois do conserto, está certa. |
| Cadastrar o link e publicar | Na gravação: o cadastro do site, a confirmação e o Publicar, contra o Netlify falso local. A publicação real foi feita depois, no mesmo projeto. |
| O resultado no ar | HTTP 200, título certo, 10 + 1 slides, `X-Robots-Tag: noindex, nofollow` e `robots.txt` com Disallow (`bruto/no-ar.json`). |

## Achados (e o que foi feito)

1. **Seguir o agente, num projeto novo** (consertado, PR #12, já na `main`): a edição recarrega o deck, e o studio o devolvia ao lugar de antes. Foi achado na primeira gravação, em 1600×900, e a regravação em 1080p já mostra o conserto.
2. **Cartão de aprovação por 10 min** (no PR de achados): no nível padrão, um `find`/`cat` só de leitura do agente pediu aprovação e prendeu o pedido por 10 min. O conserto deixa passar a leitura dentro do deck e reduz o prazo do cartão para 2 min, com o aviso no próprio cartão.
3. **Uma mensagem do agente em inglês** (no PR de achados): a regra do português foi reforçada no prompt do sistema, no `CLAUDE.md` do projeto e na skill.
4. **Edição direta** (PRs #14 e #15): o texto entrou no meio da frase. A causa era o End nativo, que vai ao fim da linha visual numa caixa que quebra (#15); o #14 cobre ainda a caixa que termina numa fórmula inline. A tomada nova está em `bruto/edicao-direta-1080p.mp4`.
5. **A gravação não aprova cartões:** o teste não aprovou nenhum pedido do agente por fora (o classificador de segurança bloqueou a tentativa, com razão). A instância de teste nega um cartão sem resposta em 30 s.

## Material

- **Bruto para a sessão de vídeos:** os vídeos em 1920×1080, sem cortes, mais o shot-list com os tempos, as esperas a cortar e uma legenda por momento. O shot-list está em [bruto/SHOT-LIST.md](bruto/SHOT-LIST.md); os vídeos ficam fora do git, em `C:\Users\Yeonatan\deck-gerador-testes\teste-ponta-a-ponta\bruto\`.
- **Pasta mock e licenças:** `C:\Users\Yeonatan\deck-gerador-testes\mock-e2e\LICENCAS.md`. Os artigos são arXiv:2609.29378 (Luque e Standing) e arXiv:2503.20086 (MacQueen, Hardy, Braun e Tyson), ambos CC BY 4.0. As notas e as imagens foram feitas para o teste (CC0).
- **O projeto gerado:** `C:\Users\Yeonatan\deck-gerador-testes\teste-ponta-a-ponta\Seminario de metodos`.
- **Scripts:** a gravação (`gravar_e2e2.py`), o Netlify falso (`fake_netlify.py`) e a conferência no ar (`gravar_no_ar.py`) ficaram no scratchpad da sessão r5-deck.

## O que espera o dono

- **Ver o resultado** e, se quiser, apagar o site de teste no Netlify (só ele ou o orquestrador, com o login).
- **O que dá para apagar depois da edição do vídeo:** `C:\Users\Yeonatan\deck-gerador-testes\e2e` (a primeira gravação, de 1600×900).
