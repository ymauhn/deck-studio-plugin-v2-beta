# Deck Studio in Python: decisions and contracts

Written 2026-10-27. This document is the contract for the Python version. Where it differs from `docs/SPEC.md`, it wins.
The SPEC's user stories, HTTP contract, Selection shape and safety rules still apply unless changed here.

## Author decisions of 2026-10-27

- **Language:** the backend is Python 3.12. The browser UI stays plain HTML, CSS and JavaScript modules. The kit's deck build stays Node (`deck/build.mjs`).
- **Default model:** Opus (`opus`, which is `claude-opus-5-5`). Sonnet and Haiku stay selectable per chat.
- **Skills:** a selected set by default, editable in a settings panel:
  - the project skills (the kit's `.claude/skills`, including skills the chat creates);
  - `frontend-design:frontend-design` and `impeccable:impeccable` (plugins);
  - `dataviz` (bundled with Claude Code);
  - `humanizer` and `thesis-review` (user skills in `~/.claude/skills`).

  No MCP servers other than the app's own deck tools.
- **Scope:** everything in the SPEC, plus the former "Out of Scope" items:
  - swapping a single slide in place;
  - Beamer mode, both paths;
  - drag and resize on the 12-column grid;
  - comment batches across slides;
  - provenance of each number.

  Still out of scope:
  - access from other machines and distribution;
  - PPTX and Typst;
  - a mobile layout;
  - git integration;
  - editing generated tables in place.
- **Test seams (approved).** Tests are written only here.
  1. **Browser and HTTP (primary).** pytest-playwright drives the real UI against a server subprocess on a random port. The server uses a kit copy and the fake agent.
  2. **Real SDK, manual.** `tests/live/`, skipped unless `STUDIO_LIVE=1`.
  3. **Safety modules.** pytest tests of the source editor, the write guard and history.
  4. **Deck studio build.** pytest tests that run node on a kit copy, including the single-part build. The clean build stays byte-identical to `tests/fixtures/build.orig.mjs`'s output.
  5. **Beamer engine.** pytest with real LaTeX, on a small fixture deck and on a copy of `beamer/academico`. Never run the kit's generated-Beamer build (`beamer/tools/build.py`).
  6. **Provenance module.** pytest on a kit copy.

## Runtime

- **Environment:** `uv` manages `.venv` from `pyproject.toml`, whose versions are pinned.
  - Run: `.venv\Scripts\python.exe -m deck_studio`.
  - Test: `.venv\Scripts\python.exe -m pytest`.
  - Add a dependency only if this document allows it.
  - Browser-side libraries may be vendored as single files under `deck_studio/ui/vendor/`, with their license header kept. Allowed: Moveable and Selecto (MIT).
- **CLI:** `python -m deck_studio [--kit PATH] [--port 0] [--data DIR] [--config JSON_FILE] [--fake-agent SCENARIOS_DIR] [--no-open]`.
  - When ready, it prints `DECK_STUDIO_URL=http://127.0.0.1:<port>/?t=<token>` on stdout and flushes.
  - **Default kit:** `C:\Users\Yeonatan\OneDrive\Desktop\nexusgo_deck_kit`.
  - **Default data:** `%LOCALAPPDATA%\deck-studio`.
  - **Default port:** 0, a random free port.
  - **Browser:** opens unless `--no-open`.
- **First statement of `__main__`:** delete every `ANTHROPIC_*` and `CLAUDE*` variable from `os.environ`. The Python SDK starts its CLI with `{**os.environ, **options.env}`; this was verified in the SDK source on 2026-10-27.
- **Event loop:** a single asyncio loop.
  - Start it with `asyncio.run(main())`, which runs `uvicorn.Server(Config(app, host="127.0.0.1", port=...)).serve()`.
  - Never use uvicorn's reload or workers.
  - On Windows this is the Proactor loop, which subprocesses need.
- **Kit commands:** run through `asyncio.create_subprocess_exec` with an argv list and `cwd` set to the kit root. Never use a shell string. Resolve `node` with `shutil.which`.
  - The job commands of the adapter config are lists. Tests replace them with harmless commands through `--config`.
- **Process trees on Windows:** stop them with `taskkill /T /F /PID <pid>`. That covers the server, builds and the claude CLI.

## Package layout and ownership

```
deck_studio/
  __init__.py
  __main__.py            CLI, env scrub, server start                       [app]
  config.py              adapter: nexus_go_config(kit), load_config(kit, config_path) (port of src/adapter.mjs)   [app]
  core/                  source_edit.py, write_guard.py, history.py (ports of src/core/*.mjs)   [safety]
  deck_build.py          DeckBuilder: studio build, state, part builds, sources_changed()       [app, then hotswap]
  edits.py               EditService: one undoable turn per direct edit                         [loop-edit]
  agent/                 session.py, fake.py, sdk.py, tools.py, prompt.py                       [app, then loop-agent, then chats]
  render.py              Renderer: headless Chromium on the studio deck (screenshots, checks)   [loop-agent]
  beamer/                engine.py (compile, render, synctex, locate, generated-deck map)       [beamer]
  provenance.py          number -> source index                                                 [provenance]
  server/                app.py (create_app), state.py, events.py, security.py, routes/*.py    [app]
  features/              one module per feature: router + optional startup; auto-included     [feature owners]
  ui/                    index.html, app.js, picker.js, style.css (moved from src/ui)          [app]
  ui/features/           <name>.js (+ optional <name>.css): auto-loaded by the shell            [feature owners]
  ui/deck/               <name>.js: auto-injected into /deck after picker.js                    [feature owners]
  ui/vendor/             vendored browser libraries
tests/
  conftest.py            kit_copy fixture (done; do not change)                                 [lead]
  helpers/kit_copy.py    make_kit_copy(src=None, extra=()), remove_kit_copy(root) (done)        [lead]
  unit/                  test_source_edit, test_write_guard, test_history [safety]; test_deck_build [kit]; test_beamer_engine [beamer]; test_provenance [provenance]
  e2e/conftest.py        studio server fixture, authenticated page fixture                      [app]
  e2e/test_*.py          one file per feature
  fixtures/              scenarios/*.json (moved from test/fixtures), build.orig.mjs, beamer/
  live/test_smoke.py     STUDIO_LIVE=1                                                          [loop-agent]
```

**Shared files rule:** an agent edits only what it owns. Outside that, it may add lines to a shared file only through the extension points below. If a shared file truly needs a change, the change is small, and the agent reports it in its result.

## Extension points (built by [app], used by everyone)

- **Server routes:** `deck_studio/server/app.py` discovers every module in `deck_studio/features/` with `pkgutil`.
  - Each module exports `router: fastapi.APIRouter`, and optionally `async def startup(state)` and `async def shutdown(state)`.
  - Feature routes live under `/api/<feature>/...`.
  - Security middleware covers them automatically.
- **App state:** `request.app.state.studio` is one `StudioState` object, the same everywhere:
  - `config`, `kit_root`, `data_dir`, `token`, `port`;
  - `events` (EventHub);
  - `builder` (DeckBuilder);
  - `history`, `guard`, `chats`, `turn_lock`;
  - `settings` (a dict persisted in `data_dir/settings.json`);
  - `selection` (the last selection list);
  - `extras` (a dict that features may use).
- **Events:** `await state.events.publish(type, **data)` sends `data: {"type": type, ...}` on `GET /api/events`.
  - The SPEC event types are unchanged.
  - New types use the feature name: `deck-swap`, `beamer`, `comments`, `job`.
- **UI features:**
  - `GET /api/ui-features` returns `{"app": [...], "deck": [...]}`. These are the URLs of `ui/features/*.js` and `ui/deck/*.js`.
  - `app.js` imports each app feature module and calls `default(studio)`. It also links `<name>.css` if that file exists.
  - The `/deck` route injects picker.js, then every `ui/deck/*.js`, before the last `</body>` of the studio deck.
- **`window.studio`:** the object passed to app features. It is created by `app.js` before features load.
  - `api(path, body?, {method}?)` returns `{status, data}`. It has the same semantics as the current `api()` helper.
  - `on(type, handler)` subscribes to SSE events, which come through one shared `EventSource`.
  - `selection`: `get()`, `set(list)`, `subscribe(fn)`, `clear()`.
  - `deck`: `frame` (the iframe), `win()`, `go(slide, step)`, `state()`, `reload()`.
  - `ui`:
    - `addToolbarButton({id, label, title, onClick, pressed?})`, which goes to the deck bar;
    - `addPanel({id, title, side: 'left'|'right'|'bottom', element})`;
    - `toast(text, kind)`;
    - `confirm(text)`, an in-page confirm dialog (never `window.confirm`).
  - `composer`: `insert(text)`, `setText(text)`, `focus()`.
  - `chat`: `send(text, {selection})`, `current()`, and `append(element)`, which adds a card to the current conversation.
  - `mode`: `get()` and `set('html'|'beamer')`, plus `subscribe(fn)`.
- **Deck-side features:** they reach the studio page as `window.parent.studio` (same origin). Picker internals stay in picker.js.
  - picker.js also exposes `window.studioPicker.selectionAt(x, y)`. It takes a point in slide units (1600x900) on the current slide and step, and returns the Selection of the topmost visible box there, or null.
- **Selections from other sources:** a selection item may carry `comment` (text from a comment batch). A Beamer TeX selection has `kind: "tex"`. The agent's prompt formatting must keep both.
- **Turn events:** `chat` `turn-end` events carry `files`, the kit-relative paths the turn changed. A direct edit publishes `edit` events `{turnId, label, files}`. Undo and diff work the same for both.

## Core module contracts

- **source_edit** [safety]: snake_case ports of `locateElement` and `replaceText`, with identical behavior. [drag] adds `set_attribute(text, line, col, name, value | None)`, with its own safety tests. It keeps every other byte, the line endings and attribute order.
- **write_guard** [safety]: `create_guard(config).check(tool_name, tool_input)` returns `Decision(behavior, reason)`, where behavior is `allow`, `ask` or `deny`. It ports the Node rules exactly.
  - [beamer] adds the hand-written Beamer project folders to `allowWrite` in the config. The generated `beamer/slides.tex` stays denied.
- **history** [safety]: a port of `createHistory`:
  - turns with ids;
  - a snapshot before the first write to each file;
  - after-content when the turn ends;
  - `diff(turn_id)` and `undo(turn_id)`, which refuses with a conflict.

  Persistence lives in `data_dir/history`.
- **EditService** [loop-edit]: `await state.edits.apply(label, files_and_fn)` runs one direct edit as an undoable turn.
  - It takes the history turn, writes the change, ends the turn, calls `builder.sources_changed(paths)`, and returns the turn id.
  - It never runs while an agent turn holds `turn_lock`; in that case it returns 409.
- **DeckBuilder** [app]:
  - `await build_studio()` runs the full studio build and publishes `build` events.
  - `state` is `{ok, ms, error, running}`.
  - `await sources_changed(paths)` decides between a part swap and a full rebuild, then publishes `deck-swap` or `deck-reload`.
  - Builds are serialized and coalesced.
  - [app] implements the full rebuild only. [hotswap] adds part builds and `deck-swap`.

## Agent

- **ChatSession:** one per chat, wrapping `ClaudeSDKClient`, or the fake client with the same methods:
  - `connect()`, `query(text_or_blocks)`, `receive_response()`, `interrupt()`, `set_model()`, `disconnect()`.
  - The fake replays the scenario JSON format of `tests/fixtures/scenarios`, which is identical to the Node fake (see `src/agent/fake-query.mjs`).
  - New fake steps: `tool`, `mcp`, `fail`, `approval`, `edit` (through the real hooks), `wait`.
- **Hooks:**
  - **PreToolUse:**
    - `guard.check`;
    - for `ask`, it publishes an `approval` event and awaits `POST /api/approvals/:id`; with no answer in 10 min, it denies;
    - before an allowed write, `history.snapshot`.
  - **PostToolUse** on writes: `builder.sources_changed`. Build errors go back as additional context.

  The permission callback is never relied on, because the user's allow rules bypass it.
- **SDK options (`agent/sdk.py`):**
  - `cwd` = kit root;
  - `model` from the chat;
  - `permission_mode="default"`;
  - `setting_sources=["project"]`;
  - `strict_mcp_config=True`;
  - `mcp_servers={"deck": <in-process tools>}`;
  - `include_partial_messages=True`;
  - `settings='{"disableAllHooks": true}'`. SDK callback hooks still fire with it; verified on 2026-10-27.
  - `env`: `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` and `ENABLE_CLAUDEAI_MCP_SERVERS=false`. Disable tool search too, so the deck tools load directly; in the spike, tool search cost one extra round trip of about 14 s. Verify the variable name live.
  - **Skills:** pass `skills=[...]` with the selected names. Pass `plugins=[{"type": "local", "path": ...}]` with the selected plugins' `installPath` from `~/.claude/plugins/installed_plugins.json`.
    - Copy the selected user skills into an app-data plugin folder (`data_dir/skills-plugin`), with a minimal plugin manifest, and pass it as a local plugin.
    - Verify live that exactly the selected skills appear in the init message.
  - **System prompt:** the Claude Code preset plus a studio appendix: selection scope, deck rules, answers in Brazilian Portuguese, and a screenshot check after edits.
- **Auth gate:**
  - **Init check:** on every init, `apiKeySource` must be `none` and the account must be on a subscription. Otherwise the chat is closed with a Portuguese error.
  - **Spike result:** the Python spike of 2026-10-27 got `apiKeySource: none` and model `claude-sonnet-5-5` on the Max plan.
- **Deck tools:** `get_selection`, `screenshot_slide`, `check_slide`, `rebuild_deck` and `add_image`, as in the SPEC. Image results are MCP image content.

## Beamer mode

- **engine.py** [beamer]:
  - `discover_projects(kit_root)` sorts projects into `handwritten` (any main `.tex` with a beamer documentclass outside the generated pair, e.g. `beamer/academico/nexus-go-academic.tex`) and `generated` (`beamer/nexus-go-defense.tex` with `slides.tex`).
  - `compile(project, work_dir, frame=None)`:
    - runs latexmk with `-synctex=1 -interaction=nonstopmode -file-line-error -outdir=<work_dir>`;
    - picks pdflatex or xelatex from the `% !TEX program` magic comment or the preamble;
    - sets `cwd` to the project folder;
    - a single frame compiles as the preamble plus that frame alone.
  - `render_page` produces a PNG through PyMuPDF.
  - `locate(page, x_pt, y_pt)` combines SyncTeX (frame level) with the text under the point, which PyMuPDF words give, matched inside that frame's source. It returns file, line, frame range, text and the method used.
  - For the generated deck, `page_map` turns each PDF page into slide id, step and kind, using `beamer/build/layout.json` and the PDF. `pdf_to_html` converts a point into the 1600x900 slide space, where 1 px = 0.1 mm.
  - It never runs `beamer/tools/build.py` and never writes in the kit. Compiles go to `data_dir/beamer/...` or a test temp dir.
- **UI** [beamer-ui]:
  - an HTML | Beamer mode switch;
  - a project list;
  - a page view with thumbnails;
  - a click selects:
    - a hand-written deck gives a TeX selection chip: `{kind: "tex", file, frame: {start, end}, line, text, page}`;
    - the generated deck gives the HTML element at the mapped point, through the deck iframe's picker, which makes a normal Selection;
  - a LaTeX source pane for the selected frame, with save through EditService and frame recompile;
  - a "Regenerar Beamer" action, which reuses the `beamer` job.

## Provenance

- **provenance.py** [provenance]: `build_index(kit_root)` returns, for each slide, each number on it with its sources:
  - `dissertation.tex` lines with a snippet;
  - or the reason from `qa/number_audit.md` (FACTS.md or an allowed exception).

  It ports the canonicalization of `qa/audit_numbers.py`; the kit file is never imported. It is served at `GET /api/provenance`.
- **Deck side** [provenance-ui]: hovering a number shows a small chip with its source. It finds the number under the pointer with `caretPositionFromPoint` and never rewrites the deck DOM.

## Contracts added during the build (2026-10-28)

The workflow's review and fix rounds, and the lead's last fixes, added these. They are tested at the seams named.

- **The studio deck's CSP** (seam 1, `test_security`):
  - `/deck` answers with `default-src 'self' data:; script-src 'nonce-<per response>' <hashes>; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'`.
  - The deck loads nothing from another server (an image or a CSS url in a slide would tell it what the agent put in the address), except the Google Fonts the NEXUS-GO shell links (`test_project_config`, 2026-10-28).
  - The hashes come from `deck/build/studio/csp.json`, which the kit's studio build writes: the shell's own scripts (data and bundle), hashed from the shell filled without slides or CSS.
  - The scripts the server injects (`picker.js`, `ui/deck/*.js`) carry the nonce. A `<script>` or an inline handler in a slide never runs with the studio's origin.
  - `DeckBuilder.current()` builds again when `csp.json` is missing or older than the deck.
- **The write guard's `askWrite`** (seam 3): writes to `deck/src/*.js`, `*.mjs`, `*.cjs` (the `*` crosses folders) and `deck/src/shell.html` need the author's approval, because they become trusted scripts.
- **The kit's build:** an image name that leaves `img/` or `svg/` (`img/../x`) is a missing asset and fails both builds (seam 4).
- **The renderer** loads only the studio deck file and aborts every other request. It calls `DeckBuilder.current()` first.
- **Beamer engine:** `latexmk -norc ... -latexoption=-no-shell-escape`. LuaLaTeX never runs; a lualatex magic comment falls back to the preamble rule. TeX runs with `MIKTEX_CORE_ALLOWUNSAFEINPUTFILES=false`: an `\input` or `\includegraphics` of a file outside the deck's folder fails (seam 5; its limits are in `docs/IMPORT.md`, Agent).
- **Turns:** `GET /api/turns` lists the turns that changed files, oldest first, as `{turnId, kind: "edit"|"agent", label, files, undone}`. After a page reload, `turns.js` draws the direct edits' cards from it and marks undone cards; agent cards come back with the chat replay.
- **Chats:** the routes are `GET/POST /api/chats`, `DELETE /api/chats/{id}`, and `POST /api/chats/{id}/messages|interrupt|model|title`.
  - A `notice` chat event tells the author that a saved SDK session could not be resumed and a fresh one started.
- **Settings:** `GET/POST /api/settings`; `settings["skills"]` is `{name: bool}`.
- **Hot swap:** the config has `partBuild` and `partOut`, and the `deck-swap` event is `{parts: [{part, css, slides: [{id, html}]}]}`.
  - `studio.deck.state()` returns null until the deck's engine starts.
- **Jobs:** they answer 409 `busy` while a turn holds the lock. A job command equal to `cleanBuild` runs under `DeckBuilder.lock`.
- **One studio per data dir:** `studio.lock` holds the running studio's URL, and a second launch prints that URL and exits.
- **Tests:** `run_studio` gives every e2e server `SAFE_JOBS`, harmless stand-ins for every job.

## Fixes from the live import run (2026-10-28)

A run of the PDF import with the real SDK found these; each is tested at the seam named.
- **SDK buffer** (seam 2, `test_smoke`): `max_buffer_size` is 64 MiB (`sdk.MAX_LINE`). One stream-json line holds a whole tool result, and an image twice; the SDK's default of 1 MiB ended a turn on the Read of a PNG.
- **A failed turn** (seam 1, `test_agent_loop`):
  - its `error` chat event says in pt-BR what happened and what to do next; `detail` holds the SDK's or the CLI's own words, which the chat folds under "Detalhe técnico";
  - a tool call still without a result when the turn ends gets a `tool` event with state `stopped` ("sem resultado");
  - `ChatSession.close()` closes the CLI's pipes, which the SDK leaves open when its reader fails mid-message (Python then printed "I/O operation on closed pipe" on stderr). The fake's `crash` step plays that failure.
- **Approval cards** (seam 1, `test_approvals`): the `summary` of an `approval` event is the tool's input whole (`summary(..., whole=True)`), shown with every line in a scrolling monospace box. Tool cards keep the first line, cut at 200 characters.
- **Chat answers** (seam 1, `test_chat`): `ui/markdown.js` draws a safe subset of Markdown (paragraphs, bold, italic, code, fenced blocks, `- ` and `1. ` lists, headings as bold lines), escaping the text first.
