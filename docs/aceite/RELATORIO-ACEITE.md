# Aceite da Fase 1: o gerador de apresentações (04/11/2026)

## Resultado

O gerador v2 passa no aceite nos dois casos:
- as 14 checagens do QA, entre elas a nova 19, que exige o diagrama e os gráficos;
- 0 números sem fonte;
- o juiz sem bloqueantes, com nota média de 2,8 (caso 1) e 2,7 (caso 2) de 3.

Pelo mesmo critério, falham na checagem 19 (0 diagramas, 0 gráficos):
- o deck do app de hoje, a linha de base;
- o gerador v1, só com texto e figuras;
- o deck mock publicado, que o dono achou "simples".

O v2 custou menos da metade do v1 no mesmo artigo.

## Os casos

| | Linha de base (app de hoje) | Gerador v1 | Gerador v2 | Gerador v2 |
|---|---|---|---|---|
| Fonte | arXiv:2609.29378 (velocidade radial) | o mesmo | o mesmo | arXiv:2509.16284 (plantio escalonado), de uma pasta |
| Slides | 28 | 23 + 3 de reserva | 24 + 2 de reserva | 21 + 2 de reserva |
| QA (check_deck, com a checagem 19) | 9 de 14 | 13 de 14 | 14 de 14 | 14 de 14 |
| Números sem fonte | 0 | 0 | 0 | 0 |
| Diagrama animado (FLUXO) | 0 | 0 | 1, com 2 rotas | 1, com 2 rotas |
| Gráficos animados | 0 | 0 | 2 BARRAS | 1 BARRAS (com negativos) e 1 PONTOS |
| Números que contam | 0 | 0 | 6 | 6 |
| Juiz | não rodou (o app de hoje não tem) | 1 bloqueante só do autor (apresentador e evento), depois de 7 rodadas | 0 bloqueantes, 3 rodadas | 0 bloqueantes, 3 rodadas |
| Tempo do agente | 856 s | 923 s + 2 rodadas de juiz pedidas à parte | 1.116 s + 210 s | 1.119 s |
| Custo | em medição (só os tokens: 21.845 de saída, 3.284.243 de cache lido) | US$ 17,58 (chat 8,55 + juiz 9,03) | US$ 8,08 (chat 5,26 + juiz 2,81) | US$ 6,96 (chat 4,46 + juiz 2,50) |

- **De onde vem o custo:** é o `total_cost_usd` que o Agent SDK devolve, gravado em `costs.jsonl`, e conta o preço da API equivalente. O gasto real sai da assinatura. O valor de um chat é acumulado na sessão, então somei só os aumentos (`custo_real.py`).
- **O que mudou de preço no v1:** o juiz do v1 rodou 7 vezes (3 falharam por um limite de buffer, já consertado) e brigou com o colchete do apresentador. A regra 3 da skill `deck-rodada-de-ajustes` resolve isso: um campo que só o autor sabe fica entre colchetes, vai para "Precisa de você" e não bloqueia.
- **A linha de base:** falha também nas checagens 3 (passos sem storyline), 8 (contraste), 16 (fontes offline) e 17 (notas sem página).

## Folhas de contato (o último passo de cada slide, tema claro)

- [0-linha-de-base.jpg](0-linha-de-base.jpg): o app de hoje.
- [1-gerador-v1-caso1.jpg](1-gerador-v1-caso1.jpg): o gerador v1, o "antes" no mesmo artigo.
- [2-gerador-v2-caso1.jpg](2-gerador-v2-caso1.jpg): o gerador v2, o "depois". O s08 é o FLUXO "do espectro ao planeta"; o s10 e o s11 são as BARRAS (espectrógrafos em escala, granulação contra o sinal de uma Terra); o s14 e o s18 têm os números que contam.
- [3-gerador-v2-caso2.jpg](3-gerador-v2-caso2.jpg): outra área. O s08 é o FLUXO do método da meta-análise; o s12 são as BARRAS com valores negativos (pragas); o s13 são os PONTOS (consórcio contra plantio escalonado); o s03 e o s07 têm os números que contam.
- [4-deck-mock-publicado.jpg](4-deck-mock-publicado.jpg): o deck no ar em deck-studio-teste-e2e-0411, feito pelo app de hoje.
- **A referência de nível, o NEXUS-GO**, fica fora do repositório, porque o conteúdo é do dono: `nexusgo_deck_kit/qa/contact-pt-light.png`. O que o v2 já alcança dele:
  - o diagrama do método com rotas e fluxo;
  - os gráficos em escala que crescem e contam;
  - a tabela que revela linha por linha;
  - os passos em todos os slides.
- **O que ainda falta para o nível do NEXUS-GO:** os interativos sob medida, como um parâmetro que o público mexe ou o exemplo numérico do texto animado. A skill `deck-componentes-interativos` diz quando escrever um componente novo, e o studio pede o sim do autor para gravar em `deck/src/components/`. O aceite não testou isso.

## O que não foi medido

- **O PDF exportado** dos decks v2 não foi aberto. As checagens rodam no HTML, e o modo de impressão põe cada componente no estado final.
- **A velocidade das animações:** a folha de contato é uma foto parada e não mostra quão rápido elas correm.
- **O tema escuro** passou na checagem 8 (contraste), mas não foi olhado a olho.

## Como reproduzir

O scratchpad da sessão r5-deck guarda:
- `rodar_gerador.py <url> <pdf ou pasta> <nome> <pasta>`: responde "pode seguir" nas paradas e nunca aprova cartões; a instância de teste nega sozinha em 30 s;
- `continuar_projeto.py`: para uma rodada a mais;
- `custo_real.py <home/projects/slug>`: para o custo.

As licenças:
- arXiv:2609.29378 e arXiv:2509.16284 são CC BY 4.0, conferidas no OAI-PMH do arXiv e anotadas em `mock-e2e/LICENCAS.md` e `caso2-pasta/LICENCAS.md`;
- as folhas de contato mostram figuras desses artigos, com a atribuição nas referências de cada deck.
