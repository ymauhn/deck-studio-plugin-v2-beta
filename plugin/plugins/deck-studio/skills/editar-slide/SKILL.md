---
name: editar-slide
description: "Abre o studio simples (o editor visual do Deck Studio, sem chat na página) e aplica no deck o que o autor selecionou e pediu nele (caixas clicadas e um pedido). Use quando o autor pedir para abrir o editor ou o studio simples, ou para aplicar a seleção do editor. Para o app completo, com chat, use deck-studio:instalar-studio."
---

# Editar pelo editor visual

1. Se o editor não está aberto, chame `mcp__plugin_deck-studio_deck__abrir_editor` e diga ao autor: clique nas caixas (Shift soma), escreva o que mudar e clique em "Enviar ao Claude".
2. Chame `mcp__plugin_deck-studio_deck__ler_selecao`. Cada item traz o `loc` (`arquivo:linha:coluna` da fonte do slide), o texto, o slide e o passo, e há também o pedido.
3. Abra cada arquivo no `loc` e mude só o que o pedido diz. Use as classes dos exemplos da skill `deck-studio:criar-apresentacao`, e todo número vem do `docs/FACTS.md`. Um pedido sobre um slide vale para os casos irmãos do deck (a skill `deck-studio:deck-rodada-de-ajustes`).
4. Chame `construir`, depois `screenshot_slide` e `check_slide` nos slides mudados, e corrija o que transbordar. O editor recarrega sozinho, no mesmo slide.
5. Responda ao autor no idioma em que ele escreve, em uma ou duas frases: o que mudou, em qual slide.
