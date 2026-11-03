# Proposta de licença (espera a escolha do dono)

Nenhum arquivo `LICENSE` foi gravado. Sem licença, o código fica com todos os direitos reservados, o que é o certo enquanto o repositório for privado. Esta página reúne o que pesa na escolha.

## O que as dependências exigem

| Dependência | Licença | Efeito |
|---|---|---|
| PyMuPDF (`pymupdf`, importação de PDF) | AGPL-3.0 ou licença comercial da Artifex | É o que mais pesa: um programa que importa PyMuPDF e é distribuído fica sob os termos da AGPL, a menos que se compre a licença comercial. |
| Moveable (`deck_studio/ui/vendor/moveable.min.js`, copiado no repositório) | MIT | Manter o aviso de copyright no topo do arquivo (já está lá). |
| claude-agent-sdk, FastAPI | MIT | Sem exigência além do aviso. |
| uvicorn | BSD-3-Clause | Idem. |
| Playwright, python-multipart | Apache-2.0 | Idem. |

As dependências não estão no repositório: o `uv sync` baixa cada uma. O `claude.exe` que vem dentro do claude-agent-sdk segue os termos da Anthropic, e cada usuário entra com a própria assinatura.

## Opções

1. **AGPL-3.0 (recomendada).** Combina com o PyMuPDF sem discussão, e quem melhorar o app, mesmo como serviço, devolve o código. Serve bem para um projeto de portfólio que mostra o código.
   Por que importa: é a única escolha que dispensa ressalvas ou troca de dependência.
2. **MIT, com uma nota sobre o PyMuPDF.** Mais aberta para quem quer reaproveitar o código. O app inteiro, distribuído com o PyMuPDF, continua sujeito à AGPL; para ficar MIT de fato, seria preciso trocar o PyMuPDF por uma biblioteca permissiva (pypdf ou pdfplumber), o que é função nova e fica para depois de 16/11.
3. **Sem licença (como está).** Público só para leitura, sem permissão de uso. Serve se a ideia é só mostrar o projeto.

## Antes de tornar o repositório público (espera o sim do dono)

- Escolher a licença e gravar o `LICENSE` com o texto oficial.
- O histórico tem o nome do dono (`docs/SPEC.md`, um teste do Beamer) e caminhos da máquina dele (`C:\Users\Yeonatan\...`, em `CLAUDE.md`, nos docs, em `DEFAULT_KIT` e nos testes). Não são segredos, mas ficam públicos.
- Nenhum segredo, chave ou token foi achado no histórico (varredura de 03/11: chaves `sk-ant-`, `ghp_`, `AKIA`, `xox`, chaves privadas, senhas, CPF e telefone). O único e-mail é o do autor dos commits.
- Nenhum deck, nenhuma dissertação e nenhum PDF estão no repositório. O kit NEXUS-GO mora fora dele, e o `.gitignore` barra `source/`, `data/`, `context/`, `*.pdf` e `nexusgo_deck_kit/`.
