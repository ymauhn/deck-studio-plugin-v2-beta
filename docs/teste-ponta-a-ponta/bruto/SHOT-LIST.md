# Shot-list do teste de ponta a ponta (material bruto, 04/11/2026)

Para a sessão de vídeos (videos-r4). O material vai virar um comercial de 2 a 5 minutos, sem as esperas, com legendas e animação de escrita.

## Os arquivos

- **Onde ficam:** os vídeos ficam fora do git, porque passam do limite de arquivo do GitHub, em `C:\Users\Yeonatan\deck-gerador-testes\teste-ponta-a-ponta\bruto\`.
- **`painel-1080p.mp4`:** a aba do studio, onde o projeto é criado. São 1920×1080, 256,8 s, H.264 crf 18.
- **`projeto-1080p.mp4`:** a aba do projeto novo, de quando abre até a publicação. São 1920×1080, 246,2 s, H.264 crf 18.
- **Originais:** os `.webm` do Playwright, sem conversão, estão em `bruto\videos\`.
- **`marcas.json`:** os tempos medidos pelo script de gravação, no relógio da gravação.
- **Relógios:** o vídeo do painel começa com a gravação; o do projeto começa 10,8 s depois. Os tempos abaixo já estão no relógio de cada vídeo e têm cerca de ±1 s.

## Momentos úteis

| # | Momento | Vídeo | Início | Fim | Legenda |
|---|---|---|---|---|---|
| 1 | Criar projeto da pasta | painel | 6,4 s | 13,0 s | Uma pasta com dois artigos, notas e imagens vira um projeto em um clique. |
| 1b | O projeto abre na aba nova | projeto | 0,0 s | 9,1 s | O Deck Studio extrai os PDFs e o agente começa a montar o deck. |
| 2 | Geração: os primeiros passos | projeto | 9,1 s | 49,1 s | O agente lê os artigos e as notas e escreve slide por slide. |
| 3 | O deck pronto e o resumo do agente | projeto | 185,2 s | 190,2 s | Em pouco mais de dois minutos, o deck sai pronto, com um resumo do que revisar. |
| 4 | Ir para o slide | projeto | 190,2 s | 196,7 s | Digite o número, ou B1 para um slide de reserva, e o deck vai direto. |
| 5 | Editar pelo chat | projeto | 196,7 s | 205,1 s | Clique numa caixa e peça a mudança em português. |
| 6 | Seguir o agente | projeto | 205,1 s | 220,2 s | O deck vai sozinho ao slide que o agente está editando. |
| 7 | Edição direta | projeto | 220,2 s | 227,5 s | Duplo clique no texto e edite ali mesmo. |
| 8 | Cadastrar link e publicar | projeto | 227,5 s | 245,5 s | Cadastre um site e publique o deck com um clique. |
| 9 | O resultado no ar | no-ar | 0,0 s | fim (cerca de 12 s) | O deck no ar, num link que se compartilha. |

**Notas**
- **Momento 7:** nesta tomada, o texto digitado entrou no meio da frase ("excentricidade (editado à mão)e semiamplitude"). É o bug do End antes de uma fórmula, que está no PR de achados. Depois do merge, uma tomada nova desse trecho vai para `bruto\` como `edicao-direta-1080p.mp4`.
- **Momento 8:** nesta gravação, o site é o Netlify falso local. A publicação real foi feita depois, pelo orquestrador, no mesmo projeto, e o momento 9 grava o resultado dela.
- **Momento 9:** `no-ar-1080p.mp4` (1920×1080) abre https://deck-studio-teste-e2e-0411.netlify.app e passa 6 slides. A conferência (`no-ar.json`) deu:
  - HTTP 200 e o título "Seminário de métodos (mock)";
  - 10 slides e 1 de reserva;
  - `X-Robots-Tag: noindex, nofollow` e o `robots.txt` com Disallow.

## Trechos de espera (cortar)

| Vídeo | Início | Fim | O que é |
|---|---|---|---|
| projeto | 49,1 s | 185,2 s | O agente gerando o deck (cerca de 2 min 16 s). Para o comercial, um corte seco, ou um trecho acelerado com "o agente escreve os slides". |
| painel | 13,0 s | 256,8 s | A aba do studio parada depois de criar o projeto; tudo segue na aba do projeto. |
| projeto | 245,5 s | 246,2 s | O fim da gravação. |

## O que o vídeo mostra, de verdade

- **O agente é real:** o Claude Opus, pela assinatura, no Deck Studio da `main` com o conserto do Seguir o agente. Nenhuma resposta foi simulada.
- **A pasta mock:** `C:\Users\Yeonatan\deck-gerador-testes\mock-e2e`, com as licenças em `LICENCAS.md`.
  - os artigos arXiv:2609.29378 (velocidade radial) e arXiv:2503.20086 (forrageamento), ambos CC BY 4.0;
  - duas notas `.md` e duas imagens desenhadas para o teste, CC0.
