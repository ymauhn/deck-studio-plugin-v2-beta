# Terceiros

O plugin instala estas dependências (no `server/pyproject.toml`, nas versões travadas do `uv.lock`), e o modelo de projeto traz as fontes abaixo, embutidas no deck.

| Componente | Uso | Licença |
|---|---|---|
| mcp (Model Context Protocol, SDK Python) | o servidor MCP do plugin | MIT |
| FastAPI | rotas do módulo Beamer reaproveitado do app | MIT |
| PyMuPDF | extrair o texto e as figuras dos PDFs; páginas do Beamer | AGPL-3.0 |
| Playwright | capturas, checagens e QA dos slides no Chromium | Apache-2.0 |
| Atkinson Hyperlegible Next | fonte do texto dos slides | SIL Open Font License 1.1 |
| Bricolage Grotesque | fonte dos títulos | SIL Open Font License 1.1 |
| IBM Plex Mono | fonte dos números | SIL Open Font License 1.1 |

Os artigos usados nos testes e exemplos de aceite são do arXiv, com licença CC BY 4.0, e os créditos estão nas referências de cada deck.
