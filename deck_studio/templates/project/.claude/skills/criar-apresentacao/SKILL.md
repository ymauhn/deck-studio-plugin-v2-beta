---
name: criar-apresentacao
description: Builds the whole talk from the PDF imported into this project, in the format that studio.json names (HTML in deck/, Beamer in beamer/apresentacao/). Use it for the first request of a new project, or when the author asks to make the talk again from the PDF.
---

# Build the talk from the PDF

Work without asking questions: make the choices yourself and list them in the summary at the end. The rules and the markup are in the project's CLAUDE.md.

The first request may end with the author's instructions (`Instruções do autor: ...`): the time of the talk, the audience, the event and its date, who presents, what to stress. They come before the defaults below.

1. **Read the PDF.**
   - Start with `context/{{SLUG}}/info.json`: the pages, title, author, and each figure with its page and caption.
   - Beamer: copy the figures the talk may use into `beamer/apresentacao/figures/` now, with one `cp` command, while the author is watching to approve it.
   - Then read `context/{{SLUG}}/texto.md`. A thesis is long: read its abstract, introduction and conclusions first, then the pages that each part of the talk needs.
   - When a figure, chart or table matters, look at its page of `{{PDF}}` with the Read tool. A figure that `info.json` does not list goes on a slide as text or a table, or in the summary as one you could not use.
2. **Outline the talk.**
   - Size: 12 to 20 slides for an article, 30 to 45 for a thesis. When the author gives a time, plan about one slide per 1 to 2 minutes.
   - Arc: title; the problem and why it matters; the goal; the method; the results, which get the most slides; the conclusions and limits; closing; then the references the slides cite.
   - A section slide opens each part. Each slide has one idea, its title states it, and its notes give the page.
3. **Write the slides in batches**, one part at a time.
   - HTML: the title slide goes in `deck/src/slides/00-title.html`, then one file per part (`01-introducao.html`, ...). Each slide copies a pattern of [padroes.html](padroes.html): title (and long title), section, bullets, figure with caption, two columns, table, quote, closing, references.
   - Beamer: fill the front matter of `beamer/apresentacao/apresentacao.tex`, then add the frames part by part, after the outline frame.
   - The authors, their institution, the event and the date come from the PDF or the author's instructions. When neither names the author (or one of the others), leave a clear placeholder in the slides' language, as the Beamer template has them (`[autor]`, or `[author]` in English), and say so in the summary. Never put a description of the work there, such as "Dissertação de mestrado": Beamer repeats `\author` in every footline.
4. **Check and fix each batch** before you start the next one.
   - HTML: run `mcp__deck__screenshot_slide` and `mcp__deck__check_slide` on every slide.
   - Beamer: run `mcp__deck__compile_beamer` until it reports 0 errors and no Overfull box in `boxes` (Underfull ones are hints only), then `mcp__deck__screenshot_beamer_page` on the new pages.
   - Fix text that overflows (cut it, or split the slide), figures too small to read, and any number that differs from the PDF.
5. **End with a short summary in Brazilian Portuguese:** how many slides and parts, and what the author should review: the choices you made, the numbers to confirm, the placeholders left for what the PDF does not say, and the figures you could not use.
