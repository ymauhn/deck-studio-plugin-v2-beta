# Importing a PDF: design and contracts (2026-10-28)

This doc extends `docs/PYTHON.md` and wins over it where they differ.

## Goal

The author's words (2026-10-28): "quero que já dê pra importar um PDF para gerar beamer ou HTML já nessa versão".

The flow:
1. In Deck Studio, the author picks a PDF (an article, a dissertation, a report).
2. The author names the project and picks HTML or Beamer and the language of the slides.
3. The app creates a new project folder from a template and extracts the PDF into it.
4. The project opens in its own studio, in a new browser tab.
5. The agent builds the presentation from the PDF there, while the author watches.
6. From then on the author edits it like the NEXUS-GO deck: select, chat, edit in place, undo, and the Beamer source pane.

## Scope

**Non-goals now:**
- the ECOS integration;
- a git repo;
- imports of PPTX or DOCX;
- choosing a theme beyond the two templates;
- runtime kit switching inside one server process: each project runs in its own studio process.

**Anti-goals.** These would make the work a failure even if the import works:
- Anything that changes how the NEXUS-GO studio behaves this week: its config, its data dir, its chats or its UI flow.
- Any test going red.
- The kit (`C:\Users\Yeonatan\OneDrive\Desktop\nexusgo_deck_kit`) being written. It stays read-only here. Tests use kit copies.

**Where the work happens:** in `C:\Users\Yeonatan\deck-studio-next`, the development copy. Never in `C:\Users\Yeonatan\deck-studio`, which the author is using. The lead swaps the copy in at the end.

## User flow

1. **The Projetos panel.** A "Projetos" button in the top bar opens a panel with two parts.
   - **The project list.**
     - The default kit comes first, named "NEXUS-GO (kit da defesa)". It is the `DEFAULT_KIT` of `__main__`, or the current kit when that is the default.
     - Then the imported projects, newest first, each with "Abrir".
   - **The form "Nova apresentação a partir de um PDF".**
     - **PDF:** a drop zone or a file picker; one `.pdf` of at most 100 MB.
     - **Nome:** defaults to the PDF's file name without the extension.
     - **Formato:** "HTML (deck web)" or "Beamer (LaTeX)".
     - **Idioma dos slides:** "Português" (the default) or "English".
     - **Pasta:** defaults to `%USERPROFILE%\Deck Studio\<Nome>`; shown and editable.
     - The button "Criar apresentação".
2. **Creating.**
   - The button first opens a blank tab synchronously, so no popup blocker gets in the way.
   - The panel shows the steps: "Extraindo o PDF…", then "Abrindo o projeto…".
   - When the server answers with the new studio's URL, the blank tab goes there.
   - If the tab could not open, the panel shows a link "Abrir o projeto".
3. **In the new tab.**
   - The project's own studio opens. Its chat already has the generation request, which the server sent as its first message, and the turn is running.
   - The deck updates live as the agent writes: in HTML, a rebuild and reload after each edit; in Beamer, a recompile on each .tex edit.
   - The start mode follows the format.
4. **Opening later.** "Projetos" → "Abrir" starts that project's studio, or reuses the running one, and opens it in a new tab.

## Project layout

Every project is made from `deck_studio/templates/project/`. Both formats get both folders; the chosen format decides the first request and the start mode.

```
<project>/
  studio.json                    the project's studio config (merged over generic_config)
  CLAUDE.md                      the agent's rules in this project
  .claude/skills/criar-apresentacao/SKILL.md
  context/<file>.pdf             the imported PDF
  context/<slug>/texto.md        extracted text
  context/<slug>/figuras/*.png   extracted images
  context/<slug>/info.json       pages, words, title guess, figures with page and caption
  deck/build.py                  stdlib-only build: studio and clean modes
  deck/src/shell.html  deck/src/engine.js  deck/src/deck.css  deck/src/slides/00-title.html  deck/src/img/
  deck/tools/export_pdf.py       Playwright PDF of the clean deck (the export-pdf job)
  beamer/apresentacao/apresentacao.tex  beamer/apresentacao/figures/  beamer/apresentacao/latexmkrc
  tools/overleaf_zip.py          zips beamer/apresentacao into exports/<slug>-overleaf.zip (the overleaf job)
```

**Placeholders.** These are filled when the project is created, by plain string replacement in the template's text files:
- `{{TITLE}}` is the Nome;
- `{{LANG}}` is `pt-BR` or `en`;
- `{{LANGUAGE}}` is "Português (Brasil)" or "English";
- `{{PDF}}` is `context/<file>.pdf`;
- `{{SLUG}}` is the slug.

## Config: generic kits (`deck_studio/config.py`)

**Loading.** `load_config(kit, config_path=None)`:
- if `<kit>/studio.json` exists, the config is `merge(generic_config(kit, studio.json's format), studio.json)`;
- otherwise it is `nexus_go_config(kit)`, unchanged;
- either way `--config` merges on top, as today.

**`generic_config(kit, fmt="html")`** has these keys. Commands use `sys.executable`, the studio's own Python, at load time.

- **Paths:**
  - `kitRoot`;
  - `slidesDir: "deck/src/slides"`;
  - `studioOut: "deck/build/studio/deck.html"`;
  - `contextDir: "context"`;
  - `imagesDir: "deck/src/img"`.
- **Builds:**
  - `studioBuild: [py, "-I", "-X", "utf8", "deck/build.py", "--studio"]`;
  - `cleanBuild: [py, "-I", "-X", "utf8", "deck/build.py"]`;
  - `partBuild: None`: no hot swap; an edit means a full build and a deck reload.
- **`fontsCss: None`:** `/ui/fonts.css` then answers an empty stylesheet with 200.
- **Writes:**
  - `allowWrite: ["deck/src/**", "context/**", ".claude/skills/**", "beamer/**"]`;
  - `denyWrite: ["studio.json", "deck/build/**", "deck/dist/**", "exports/**", "beamer/*latexmkrc"]`: the `*` crosses folders, so this rule covers `.latexmkrc` too;
  - `askWrite: ["deck/src/*.js", "deck/src/*.mjs", "deck/src/*.cjs", "deck/src/shell.html", "deck/build.py", "deck/tools/**", "tools/**", "CLAUDE.md", "**/CLAUDE.md", "*/.claude/*"]`: Claude Code reads a `CLAUDE.md`, or a `.claude` folder below the project's own, in any folder it works in as instructions (fix round, 2026-10-28);
  - `askWriteDirs` and `readDirs`: the user skills, as in the NEXUS-GO config.
- **Jobs**, by format (fix round, 2026-10-28; the other format's folder is the untouched template):
  - html: `jobs: {"export-pdf": [cleanBuild, [py, "-I", "-u", "deck/tools/export_pdf.py"]]}`;
  - beamer: `jobs: {"overleaf": [[py, "-I", "-u", "tools/overleaf_zip.py"]]}`. The Beamer PDF is the Beamer view's: "Abrir PDF" (see UI);
  - `jobOutputs: {"export-pdf": "deck/dist/deck.pdf"}`;
  - `publishSite: None`.
- **Project:**
  - `title`: the project name;
  - `format: "html" | "beamer"`;
  - `language: "pt" | "en"`;
  - `startMode`: `"beamer"` when the format is beamer, else `"html"`;
  - `beamerStart: "beamer/apresentacao/apresentacao.tex"`.
- **Agent:** `promptRules`, the rules paragraph of the agent appendix, and `promptKinds` and `promptBehavior` (see Agent).
- **`provenance: false`.** NEXUS-GO keeps it on, through `nexus_go_config` with `provenance: true`.

**`/api/status`** adds `project: {title, format, startMode, beamerStart, provenance, jobs: [names]}`. For NEXUS-GO it gives:
- `title` "NEXUS-GO";
- `format` "html";
- `startMode` "html";
- `beamerStart` null;
- `provenance` true;
- `jobs`: its job names.

## CLI and processes (`__main__.py`, `deck_studio/projects.py`)

**New flags:**
- `--home DIR`: Deck Studio's home, holding the registry `projects.json` and the projects' data dirs `projects/<slug>/`. It defaults to the `--data` dir, so tests that pass a temp `--data` never touch the real home.
- **Without `--data`** (fix round, 2026-10-28): the default kit runs on `%LOCALAPPDATA%\deck-studio`, which is also the home. A project (a kit with a `studio.json`) runs on `<home>/projects/<slug>`, its registry entry's; one the registry does not have refuses to start, in pt-BR. A project never runs on NEXUS-GO's data dir.
- `--parent-pid PID`: a watchdog thread exits the process (`os._exit(0)`) when that process ends. Use `OpenProcess(SYNCHRONIZE)` and `WaitForSingleObject` through ctypes.

**Starting a child studio.** The command is:

```
[sys.executable, "-m", "deck_studio", "--kit", folder, "--data", <home>/projects/<slug>, "--home", home,
 "--port", "0", "--no-open", "--parent-pid", str(os.getpid()), *passthrough]
```
- `passthrough` repeats the parent's own `--fake-agent X` and `--config Y` when it was given them, so in tests the children are fake and safe too.
- **Window:** `CREATE_NO_WINDOW`.
- **URL:** read from stdout's `DECK_STUDIO_URL=` line, waiting up to 60 s; then keep stdout drained in a thread.
- **Reuse:** if `<data>/studio.lock` holds a URL and its lock is taken, open that URL instead of starting another studio. A second studio refuses to start on the same data dir; it prints the URL and exits, and that answer can be read too.
- **Shutdown:** on parent shutdown, kill the children it started (`taskkill /T /F`). They also exit through `--parent-pid` if the parent dies hard.

## Registry (`<home>/projects.json`)

- The registry is a list: `[{name, slug, path, format, language, created}]`.
- Writes are atomic: a temp file, then `os.replace`, under the home's registry lock (Review fixes). The default kit is never stored.
- **Slug:** lowercase ASCII from the name (accents removed), with `-` between words, at most 40 characters. It is unique within the registry and among the home's data dirs (`projects.reserve()`): `-2`, `-3` and so on.

## HTTP (`deck_studio/features/projects.py`)

**`GET /api/projects`** answers:

```
{current: {name, path},
 projects: [{name, slug, path, format, language, created, running, url, here?, missing?}],
 projectsFolder}
```
- The default kit comes first, as an entry `{name: "NEXUS-GO (kit da defesa)", path, format: "html", builtin: true, running, url}`, unless it is the current kit. Its studio is the one that holds the home's own `studio.lock`.
- Then the registered projects, newest first.
- `url` is set only when that project's studio is running (read from its lock file).
- `here: true` marks this studio's own project, and `missing: true` one whose folder is gone.
- `projectsFolder` is where new projects go: `config["projectsFolder"]` (the e2e tests set a temp folder), else `%USERPROFILE%\Deck Studio`.

**`POST /api/projects/import`**
- **Request:**
  - the body is the raw PDF;
  - headers: `x-file-name` (URL-encoded UTF-8) and `content-type: application/pdf`;
  - query: `name`, `format` (html | beamer), `language` (pt | en), an optional `folder` (an absolute path) and an optional `notes` (the form's "Instruções para o agente", at most 1000 characters).
- **Validation.** Each failure answers 400 `{error, message}`, in pt-BR, and leaves nothing behind:
  - the name is a plain name (reuse `files.plain`): `bad-name`;
  - the format and the language are known: `bad-format`, `bad-language`; the notes fit: `bad-notes`;
  - `x-file-name` is a plain `.pdf` name: `bad-file`;
  - the body is at most 100 MB (`too-large`) and starts with `%PDF-` (`not-pdf`); the PDF opens, has no password and extracts in under 120 s (`bad-pdf`);
  - the folder is absolute and on a disk of this PC (`bad-folder`), short enough (`long-folder`), does not exist or is empty (`folder-not-empty`), and is not inside the current kit, the default kit or another registered project (`folder-inside`); the rules are in Review fixes. A folder that cannot be written answers `folder-error`.
- **Steps:**
  1. Copy the template and fill the placeholders.
  2. Write `studio.json`: `{title, format, language, startMode, beamerStart}`.
  3. Save the PDF in `context/`.
  4. Extract into `context/<slug>/`, in a process of its own (`python -m deck_studio.pdf_import <pdf> <out>`).
  5. Register the project, then publish a `projects` event `{step: "opening", name}`: the panel's second step.
  6. Start the child, or reuse the studio that runs on its data dir.
  7. Create a chat in the child (`POST /api/chats`) and send the first message (`POST /api/chats/{id}/messages`), with the child's token in `x-studio-token`.
  8. Answer 201 `{project, url, warning?}`. The `url` ends with `#chat=<id>`, the chat of the first request.
- **Failures after the folder is made** answer 500 `{error, message}` in pt-BR:
  - `no-register`: the registry could not be written. The folder and the slug's data dir go.
  - `no-studio`: the child did not start. The project stays in the list, to open again.
  - `no-request`: the first message did not reach the child. The project stays in the list.
- **The first message** is `config["importMessage"]`, formatted with `pdf`, `format`, `format_name`, `language`, `text` and `figures`; the scanned-PDF line and the author's notes follow it (Review fixes). The default text:

  > Crie a apresentação a partir do PDF `{pdf}`, no formato {format_name}, com os slides em {language}. O texto extraído está em `{text}` e as figuras em `{figures}`. Siga a skill criar-apresentacao e o CLAUDE.md do projeto.

  E2E tests put a `#scenario:` marker in front of it through `--config`.

**`POST /api/projects/open`** takes `{path}` and answers `{url}`: it starts the project's studio or reuses the running one. The `path` must be a registered project or the default kit: else 404 `not-found`, and 404 `missing` when its folder is gone; a studio that does not start answers 500 `no-studio`.

**`POST /api/projects/remove`** takes `{path}` and answers `{path}` (Review fixes); 404 `not-found` when it is not registered.

All four are ordinary studio routes, behind the token and the Origin check.

## PDF extraction (`deck_studio/pdf_import.py`)

`extract(pdf_path, out_dir) -> info dict`, using PyMuPDF (`import pymupdf`).

- **`texto.md`:**
  - It starts with `# <title guess>`.
  - Then each page gets `## Página N` and its text blocks in reading order.
  - A block whose spans are at least 1.3 × the median body font size becomes `### <text>`.
- **`figuras/`:**
  - The embedded images, each xref once.
  - An image is kept only when width and height are both at least 150 px.
  - Images are saved as PNG `p{page:03d}-{n}.png`; CMYK and alpha are converted to RGB.
  - At most 300 images in all.
- **`info.json`:** `{pages, words, title, author, figures: [{file, page, width, height, caption}]}`.
  - `title` is the metadata's title when it has two words or more, all on the first page with text; else the longest run of lines in that page's largest type, without the front matter's headings (Resumo, Abstract, Sumário, Agradecimentos, Lista de…; live-run fixes); else the PDF's file name.
  - `caption` is the nearest text line on the same page starting with "Figure", "Figura" or "Fig.", else null.
- **Speed:** a 145-page dissertation must take under 30 s.
- **Safety:** the PDF is untrusted data. Never execute anything from it, and cap the sizes.

## Templates (`deck_studio/templates/project/`)

**HTML deck:**
- **`engine.js`:** a copy of the NEXUS-GO kit's `deck/src/engine.js`. It is ours; read it from the kit.
  - The component registry is optional.
  - The studio relies on this DOM and API: `window.deck` (`go`, `state`, `steps`, `overview`), the `deck:change` event, `#deck` with `ov` in overview, `#stage section.slide`, the fragments, notes, overview and presenter.
  - None of it may change.
- **`shell.html`:**
  - the kit shell's structure, with no NEXUS-GO texts and `lang="{{LANG}}"`;
  - its placeholders: `/*__CSS__*/`, `<!--__SLIDES__-->` and one inline module script with `/*__JS__*/`.
- **`deck.css`:** a neutral and distinctive academic or business theme, for a 1600×900 canvas.
  - It has light and dark themes and uses system font stacks (works offline).
  - The body is the 12-column grid `.bd`, as in the kit, with named column classes, so the drag feature works.
  - Its patterns: title slide, section slide, bullets, figure with caption, two columns, table, quote, closing.
  - Use the frontend-design guidance; avoid the generic AI look.
- **`build.py`:** stdlib only.
  - Usage: `python -I -X utf8 deck/build.py [--studio]`.
  - It reads `deck/src/slides/*.html` in name order.
  - **Studio mode:**
    - it inserts `data-loc="deck/src/slides/<file>:<line>:<col>"` into every element start tag of the slide files;
    - line and col are 1-based and point at the tag's `<`, which is exactly what `core/source_edit.py` resolves (as parse5 gave it);
    - `src="img/..."` becomes a data URI; a name that leaves `deck/src/img` fails the build;
    - it writes `deck/build/studio/deck.html` and `deck/build/studio/csp.json`;
    - `csp.json` holds `{scripts: ["'sha256-…'"]}`, the hashes of the shell's inline scripts as filled without slides or CSS, CRLF normalized to LF (as in the kit's `build.mjs`).
  - **Clean mode:** writes `deck/dist/deck.html` without data-loc.
  - It must take under 1 s for 40 slides.
- **`00-title.html`:** one title slide with `{{TITLE}}`.
- **`deck/tools/export_pdf.py`:** Playwright (chromium), one page per slide at the final state of its steps → `deck/dist/deck.pdf`.

**Beamer:**
- **`apresentacao.tex`:**
  - pdfLaTeX, 16:9;
  - a clean theme in the look of `beamer/v2-colegas` in the kit (Madrid-like navy, Latin Modern Sans, a footline with author, title and n/N), but generic: no Unicamp logos;
  - `\title{{{TITLE}}}`, `\author`, `\institute` and `\date` filled with placeholders in the slides' language (`[autor]`, `[instituição]`, `[evento e data]`; live-run fixes) that the agent replaces from the PDF or the author's instructions;
  - a title frame and an outline frame;
  - `\graphicspath{{figures/}}`.
- **`latexmkrc`:** `$pdf_mode = 1;`, for Overleaf. The studio compiles with `-norc` anyway.
- **`tools/overleaf_zip.py`:** zips `beamer/apresentacao`, without build files, into `exports/<slug>-overleaf.zip`, and prints the zip's absolute path in UTF-8 (live-run fixes).

**`CLAUDE.md` of the project.** In English for the agent, with the author-facing language noted:
- Talk to the author in Brazilian Portuguese; the slides are in `{{LANGUAGE}}`.
- **Sources:** every number, name and claim on a slide comes from the imported PDF `{{PDF}}`; never invent results. Put the source page in the slide's notes.
- **Style:** short bullets, one idea per slide, no em dashes.
- **Figures:**
  - in HTML, use those in `context/{{SLUG}}/figuras` through `mcp__deck__add_image`;
  - in Beamer, copy them into `beamer/apresentacao/figures/`.
- **How to write:**
  - **HTML:** `section.slide`; a header `h2`; the `.bd` grid with the column classes; fragments with `.f` and `data-f`; notes in an `aside`. Name it as the engine expects.
  - **Beamer:** frames, overlays, figures.
- **Check every slide:**
  - **HTML:** `mcp__deck__screenshot_slide` and `mcp__deck__check_slide`.
  - **Beamer:** `mcp__deck__compile_beamer` and `mcp__deck__screenshot_beamer_page`.

**The skill `criar-apresentacao`:**
1. Read `info.json` and `texto.md`. Look at key PDF pages with the Read tool when figures or tables matter.
2. Outline the talk without asking:
   - 12 to 20 slides for an article;
   - 30 to 45 for a thesis;
   - about one slide per 1 to 2 minutes.
3. Write the slides in batches.
4. Check and fix them.
5. End with a short summary in pt-BR: what was made and what to review.

## Agent (`agent/tools.py`, `agent/prompt.py`)

**New deck tools:**
- `compile_beamer(path?)`:
  - It compiles the project's Beamer deck: `path`, else `config["beamerStart"]`, else the only hand-written project.
  - It uses the same compile as the Beamer view, so the screen updates too.
  - It answers `{ok, pages, errors: [{file, line, message}], boxes: [{file, line, message}]}`; `boxes` came with the live-run fixes.
- `screenshot_beamer_page(page, path?)`: a PNG of a page of the last compile.

**Live compiles** (fix round, 2026-10-28): after each tool call of an agent turn, an opened hand-written deck whose `.tex` files changed compiles again (`features/beamer.py` `watch()`, on the `chat` `tool` events), as well as at the turn's end.

**TeX's inputs** (fix round, 2026-10-28): the compile runs with `MIKTEX_CORE_ALLOWUNSAFEINPUTFILES=false`, so `\input`, `\include` and `\includegraphics` of an absolute path or a `../` path from the deck's folder fail. Known limit: MiKTeX does not apply it to TeX primitives (`\@@input`, `\openin` with `\read`) nor to `../` names it finds from the output folder; only a sandboxed compile would close those.

**Prompt:** the appendix's rules line comes from `config["promptRules"]`.
- NEXUS-GO keeps its current text verbatim.
- The generic text says to follow the project's CLAUDE.md and the slide rules there.
- The appendix also names the protected paths from the config instead of the NEXUS-GO list.
- Its line on the selection's kinds and the sentence on where behavior goes come from `config["promptKinds"]` and `config["promptBehavior"]` (fix round, 2026-10-28): NEXUS-GO's are its own words; a project's deck has no components and no tables from a dissertation.

## UI

- **Projetos:** `ui/features/projects.js` and `projects.css`, as described in User flow. Strings in pt-BR.
- **The project's name:** in the top bar, next to "Deck Studio", and in `document.title`, so tabs can be told apart.
- **Start mode.** When `project.startMode` is "beamer":
  - the studio opens in Beamer mode;
  - `beamerStart` is open;
  - it compiles on open, as today;
  - a `beamer` event that came while the open request was answered still shows (fix round, 2026-10-28).
- **Abrir PDF** (fix round, 2026-10-28): in the Beamer bar of the project's own deck (`beamerStart`, so never in NEXUS-GO), a link to the PDF of its last good compile of the whole deck, `GET /api/beamer/projects/{id}/pdf?v=<view version>`, opened in a new tab.
- **Jobs:**
  - one button per job the project has (by format: see Config);
  - labels: the existing ones, plus `overleaf` = "Exportar para Overleaf";
  - a job's output path shows in its log.
- **Provenance:** the "Origem" button only when `project.provenance` is true.

## Tests (approved seams only)

- **Seam 1 (e2e, primary):**
  - Import a small PDF made in the test with PyMuPDF: a title, two headings, a sentence with a number, an embedded PNG.
  - Use the fake agent with `--home` at a temp dir; the `run_studio` data dir is the home.
  - Check:
    - the project folder has the template;
    - `texto.md` has the PDF's text, and `figuras/` has the image;
    - `/api/projects` lists the project;
    - the child's URL opens a studio whose title is the project's;
    - its chat shows the first request, and the fake scenario writes a slide that the deck then shows;
    - "Abrir" again reuses the running child;
    - bad inputs answer 400 in pt-BR;
    - a Beamer import opens in Beamer mode with the template compiled.
  - The whole existing suite stays green: that is the NEXUS-GO studio, unchanged.
- **Seam 3 (safety):** `generic_config`'s guard rules. Deny `studio.json` and the build outputs; ask for the deck's code and the tools.
- **Seam 4 (deck build):** the template's `build.py`:
  - every data-loc resolves to its source element through `core/source_edit.py`;
  - an image name that leaves `img/` fails the build;
  - the clean build has no data-loc;
  - the deck runs under the CSP in the studio, which the e2e tests cover.
- **Seam 5 (Beamer):**
  - the template `.tex`, filled, compiles with real pdfLaTeX with 0 errors;
  - `compile_beamer` reports a broken frame's file and line.
- **Seam 2 (live):** the lead runs it at the end with the real SDK: a short real PDF, in HTML and in Beamer.

**Processes:** no test leaves a process or a temp folder behind. `run_studio`'s `taskkill /T` covers the children, and `--parent-pid` is the backstop.

## Ownership (parallel builders)

- **[config]:**
  - `config.py`: `generic_config`, `load_config` and `nexus_go_config` (adds `provenance: true`, `promptRules` and `title`);
  - `__main__.py`: `--home`, `--parent-pid`;
  - `server/state.py`;
  - `server/routes/core.py`: fonts and the `/api/status` project;
  - `agent/prompt.py`;
  - `features/provenance.py` and `ui/features/provenance.js`: gating;
  - `features/jobs.py` and `ui/features/jobs.js`: dynamic buttons and labels;
  - `ui/app.js`: the project title and the startMode hook (`studio.project`);
  - `ui/index.html`;
  - its tests.
- **[templates]:** `deck_studio/templates/project/**` and `tests/unit/test_template_build.py` (seam 4), plus a seam-5 test that the filled template compiles.
- **[extract]:** `deck_studio/pdf_import.py`. Its behavior is tested through [projects]' e2e tests; [extract] may add one e2e-free check in the [projects] test module if needed.
- **[beamer-tools]:**
  - `agent/tools.py`: the two tools;
  - `features/beamer.py`: a shared compile entry point, plus opening `beamerStart` at start;
  - `ui/features/beamer.js`: start mode;
  - tests at seam 5 and seam 1 (a fake scenario calling `compile_beamer`).
- **[projects]:**
  - `deck_studio/projects.py`: registry, create, children;
  - `features/projects.py`;
  - `ui/features/projects.js` and `projects.css`;
  - `tests/e2e/test_projects.py`;
  - `tests/fixtures/scenarios/import-*.json`.
- **[lead]:** `tests/e2e/conftest.py` and `tests/helpers`. Any shared change goes through the lead: say what you need in `shared_file_changes`.

## Review fixes (2026-10-28)

The review round changed these contracts. `tests/e2e/test_projects.py` covers each one.

- **The project folder**, besides the rules in HTTP:
  - it is on a disk of this PC (`C:\...`, or `\\?\C:\...`); a share such as `\\localhost\C$\...` is refused before `resolve()`, which would reach it over the network;
  - it is compared in one spelling: resolved, without the `\\?\` prefix that `resolve()` keeps for a name that ends in a space or dots;
  - it has at most 150 characters (`long-folder`), since Windows paths stop at 260 here (LongPathsEnabled is 0);
  - it has none of `% ~ $ { }`, which latexmk refuses in a path.
- **The default folder** is `<projects folder>\<Nome>` without `% ~ $ { }`. With no `folder`, or with that default one, an import goes to the first free of it, `<Nome> (2)`, `<Nome> (3)`...
- **Short names:** the slug stops at 40 characters, cut before a word, and a slug that Windows reserves for a device ("Nül" makes `nul`) takes the next suffix. The PDF is saved under its own name, cut at 60 characters before a word.
- **Studios that share a home:**
  - `projects.reserve()` makes the slug's data dir `<home>/projects/<slug>` first, so two studios never take one slug;
  - `projects.register()` re-reads and writes the registry under a lock on `<home>/projects.lock`;
  - `save_registry` retries the replace while a reader has the file open.
- **The first request:**
  - the query's `notes` (at most 1000 characters; the form's "Instruções para o agente") ends it as `Instruções do autor: ...`;
  - the message's fields add `format_name` (HTML or Beamer), which the default text uses;
  - a PDF with fewer than 5 words per page adds a line telling the agent to read its pages, and the 201 answer gets a `warning`.
- **Opening:**
  - `/api/projects/open` answers the URL with `#chat=<id>`: the chat whose turn runs, else the one used last;
  - a studio that is still starting (its lock taken, no URL yet) is waited for, up to 60 s.
- **The list:**
  - `GET /api/projects` marks a project whose folder is gone with `missing: true`;
  - `POST /api/projects/remove {path}` takes a project off the list and answers `{path}`. Its folder and data dir stay.
- **Other UI:** in a Beamer project, the Files pane does not mark `beamer/apresentacao` read-only. The Beamer view's back button is "Voltar à lista", since the top bar has "Projetos".

## Review fixes: extraction and templates (2026-10-28)

`tests/e2e/test_projects.py` (its last section, the extraction alone) and `tests/unit/test_template_build.py` cover each one.

- **Extraction:**
  - a soft mask's declared pixels count in the caps with its image's, so an oversized mask is never decoded;
  - an image of a single colour (a blank, or a mask the PDF draws a figure through) is not kept;
  - each figure caption that no kept image took gets its figure rendered from the page at 200 dpi, as `figuras/p{page:03d}-fig-{number}.png` (`p028-fig-2-4.png`): the ink nearest above the caption, else below it (ABNT), within the running text's column, with the short text lines that touch it. The ink is found on a 36 dpi render, never through the page's paths, and a page with an image or soft mask over the per-image cap is never rendered. Renders count in the image and pixel caps;
  - `texto.md`: a table gets a line per row; a block longer than 1000 characters breaks at line ends (Claude Code's Read cuts lines at 2000); a word broken at a line end is joined when the PDF has it unbroken elsewhere, else it keeps its hyphen (`adotou-se`).
- **Templates:**
  - the deck's own words (notes bar, help, presenter view) follow `{{LANG}}`, through the `UI_*` placeholders that `fill_template` fills;
  - `deck/build.py` locates nothing inside `textarea`, `title`, `xmp`, `plaintext`, `noscript`, `iframe`, `noembed` and `noframes`;
  - `padroes.html` adds a long title (`h2.title.long`, 72 px) and a references slide (`ol.refs` on a backup slide); every pattern fits its slide;
  - the project's `CLAUDE.md`: works the PDF cites go on a slide as "Silva et al. (2021)", and on a references slide; numbers keep their digits, and the decimal separator follows the slides' language; a figure missing from `info.json` is read from its page; in Beamer, the figures are copied with one `cp` at the start, while the author watches.

## Integration (2026-10-28)

- **Checked by hand** with Playwright and the fake agent, on a kit copy:
  - the Projetos panel; an HTML import of a real 55-page PDF and a Beamer import, each opening its new tab on its first request; the generated slide and its undo, which the deck and the Beamer view follow; Abrir again, which reuses the running studio;
  - the NEXUS-GO studio next to the app in use: the same screens, its 53 slides with no CSP violation, and `beamer/academico` compiled to the same 55 pages and text with and without the TeX input guard. Its only changes are the planned ones: the project's name and Projetos in the top bar, the tab's title `NEXUS-GO · Deck Studio`, and "Voltar à lista" in the Beamer view.
- **Known limits:**
  - In the e2e tests a project's studio gets its parent's `--config` (passthrough), so the stand-ins of NEXUS-GO's jobs merge into its own jobs, and its top bar also shows NEXUS-GO's buttons (Regenerar Beamer, Exportar PDF, Publicar). The real app passes no `--config`: a project shows only its own jobs.
  - In the tests the home's `studio.lock` belongs to the module's studio, which runs on a kit copy: "NEXUS-GO (kit da defesa)" shows "aberto", and its Abrir opens that same studio. With the real home, that lock is the NEXUS-GO studio's.
  - The Files pane refreshes when an agent turn ends, not after an undo: an undone new file stays listed until the next turn or a reload, as in the app in use.

## Fixes from the live import run (2026-10-28)

The lead's run of the import with the real SDK (seam 2: a 5-page excerpt of the dissertation, as HTML and as Beamer) found these. Each fix is tested at the seam named.

**In every studio's chat** (contracts in `docs/PYTHON.md`, "Fixes from the live import run"):
- The SDK reads lines of up to 64 MiB. Before, the HTML import's first turn ended when the agent Read Figure 5.6 (`p005-1.png`, 2516×3960 px): that tool result was one line over the SDK's default of 1 MiB.
- A failed turn says in pt-BR what happened and what to do next. The SDK's or the CLI's own words fold under "Detalhe técnico", and a tool card left without a result turns grey with "sem resultado".
- An approval card shows the tool's whole input, every line, in a box that scrolls.
- The agent's answers show their Markdown (bold, lists, code); the author's messages stay plain text.

**In the import:**
- **`compile_beamer`'s boxes** (seam 1, `test_beamer_project`). The answer adds `boxes: [{file, line, message}]`, with TeX's own words, such as "Overfull \vbox (7.97742pt too high)":
  - every overfull box over 1 pt, and every underfull box TeX reports (TeX gives those a badness, which it reports over 1000, not a size);
  - the file is the one TeX was reading, from the log's file stack (`features/beamer.py` `boxes_of`), so a box in an `\input` part names that part;
  - the log is read inside the compile lock, of full compiles only, so the answer always matches its own compile.

  The project's `CLAUDE.md` and the skill say to compile until there are 0 errors and the `boxes` list is empty. A frame a few points too tall runs into the footline, as a figure at `0.7\textheight` with a two-line caption did in the live run.
- **The Beamer deck's placeholders** (seam 5, `test_template_build`). `\author`, `\institute` and `\date` come from the `UI_AUTHOR`, `UI_INSTITUTION` and `UI_EVENT` words: `[autor]`, `[instituição]` and `[evento e data]` in a pt-BR deck, and `[author]`, `[institution]` and `[event and date]` in English. When neither the PDF nor the author's instructions name the author, the agent keeps the placeholder and says so in its summary. It never writes a description of the work there, such as "Dissertação de mestrado", which Beamer repeats in every footline.
- **The Files pane of a Beamer project** (seam 1, `test_beamer_project`). `beamer/apresentacao` comes first and open, with its main `.tex` (`beamerStart`) marked as the current file. The HTML template's `deck/src/slides` stays closed. HTML projects and the NEXUS-GO studio keep their pane as it was.
- **The Projetos panel** (seam 1, `test_projects`). The form's fields scroll on their own. A bar at the bottom holds the error, the steps, "Pronto", the hint and "Criar apresentação", so the button stays in view during and after an import.
- **Exportar para Overleaf** (seam 4, `test_template_build`). `tools/overleaf_zip.py` prints the zip's absolute path, in UTF-8. The job runs with `-I` and without `-X utf8`, so the Windows code page had turned the accents of a folder name into "�" in the Tarefas log.
- **The title guess** (seam 1, `test_projects`). `info.json`'s `title`, which heads `texto.md`, skips the front matter's headings: Resumo, Abstract, Sumário, Contents, Agradecimentos, Acknowledgements, Lista de…, List of…, Dedicatória, Prefácio and the like. When the first page's largest type holds only such a heading, the title is the PDF's file name. The live run's excerpt, which starts at its Resumo, is now titled "NEXUS-GO_dissertacao_trecho", not "Resumo".

**Checked again with the real SDK** after the fixes: an HTML import of the same excerpt, whose "Instruções para o agente" asked for Figure 5.6 on a slide, looked at first.
- The agent Read `figuras/p005-1.png`; that tool result is a 1,268,668-byte line in the CLI's transcript, over the old 1 MiB limit.
- The first turn ended normally after 71 s: 5 slides, with Figure 5.6 on slide 3. The chat showed no error, the pages had no console error, no approval was asked, and the studio printed nothing on stderr.
- On screen:
  - the agent's summary is drawn from its Markdown, in light and dark;
  - the Projetos panel keeps its steps, "Pronto" and "Criar apresentação" in view;
  - the Files pane of an HTML project is as before.
- The title slide keeps `[autor]`, `[instituição]` and `[evento e data]`, and the summary says so.
