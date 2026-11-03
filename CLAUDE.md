# Deck Studio: project rules

Local AI editor for HTML and Beamer slide decks.
- **Specs:** the spec of record is `docs/SPEC.md`, and `docs/PYTHON.md` holds the Python decisions and contracts. Where they differ, PYTHON.md wins. Read both before changing anything.
- **Visual reference:** the UI follows the architecture page (wireframe "A tela"), saved at
  `C:\Users\Yeonatan\AppData\Local\Temp\claude\C--Users-Yeonatan-OneDrive-Desktop-nexusgo-deck-kit\66bde532-395a-4c6a-9bb7-c233daf130f2\scratchpad\deck-studio\deck-studio.html`.

## Stack

- **Backend:** Python 3.12 in `deck_studio/`, with FastAPI, uvicorn and the Claude Agent SDK for Python. `uv` manages `.venv` from `pyproject.toml`, whose versions are pinned.
- **UI:** plain HTML, CSS and JS modules in `deck_studio/ui/`.
- **Commands:**
  - run: `.venv\Scripts\python.exe -m deck_studio`;
  - test: `.venv\Scripts\python.exe -m pytest`.
  - live SDK smoke (uses the subscription): `$env:STUDIO_LIVE=1; .venv\Scripts\python.exe -m pytest tests/live -s`.
- **History:** a first Node version was deleted on 2026-10-28 after the Python one passed. Do not bring Node code back into the app; the kit's own build stays Node.

## Target deck

- **Deck kit:** `C:\Users\Yeonatan\OneDrive\Desktop\nexusgo_deck_kit` (on OneDrive; paths may contain spaces; quote them).
- **Read-only:** the kit's own rules (its CLAUDE.md) apply. The dissertation sources (`source/`) and `data/` are read-only. Generated files (`deck/dist`, `deck/build`, `beamer/slides.tex`) are never edited by hand.
- **Kit changes:** the only kit files this project may change are `deck/build.mjs` (studio mode, part builds) and `deck/package.json`. No git commits anywhere.

## Testing (TDD, seams approved by the author on 2026-10-27)

Tests are written only at these seams. The list with details is in `docs/PYTHON.md`.
1. **Browser and HTTP (primary).** pytest-playwright drives the real UI against a server subprocess on a random port. It uses a kit copy and the fake agent. Lives in `tests/e2e`.
2. **Real SDK, manual.** `tests/live/`, skipped unless `STUDIO_LIVE=1`.
3. **Safety modules.** The source editor, write guard and history (`tests/unit`).
4. **Deck studio build.** It includes the single-part build. The clean build stays byte-identical to `tests/fixtures/build.orig.mjs`'s output.
5. **Beamer engine.** Real LaTeX on a fixture deck and on a copy of `beamer/academico`; never the kit's generated-Beamer build.
6. **Provenance module.** Tested on a kit copy.

How to write them:
- Work in vertical slices: one failing test, then the minimum code to pass, then the next test.
- Test behavior through public interfaces only.
- Expected values come from the spec or from known literals. Never recompute them the way the code does.

## Hard rules for code and tests

- **Never use the real kit in tests.** Tests use `tests/helpers/kit_copy.py` (`make_kit_copy`, `remove_kit_copy`), never junctions or symlinks.
- **No real publishing or generated-Beamer runs in tests.** Tests never publish to Netlify and never run `beamer/tools/build.py`. Job commands come from config, and tests replace them with harmless commands.
- **API key:** the API key must never be used.
  - The server deletes every `ANTHROPIC_*` and `CLAUDE*` variable from its own environment at startup. Every SDK or `claude` child runs without them.
  - Never read `~/.claude/.credentials.json`. Never print secrets.
- **Server scope:** the server binds to 127.0.0.1 only and requires the per-launch token.
- **Windows:**
  - quote paths;
  - use argv lists and never `shell=True`;
  - stop process trees with `taskkill /T /F`;
  - use `python -I` for kit Python tools;
  - normalize paths before comparing them (case, slashes, `..`).
- **Language:** UI strings are in Brazilian Portuguese. Code, comments, test names and docs are in English.
- **Dependencies:** only what `pyproject.toml` pins, plus the browser libraries `docs/PYTHON.md` allows. Ask before adding more.
- **App data:** under `%LOCALAPPDATA%\deck-studio`, or under the `--data <dir>` given in tests. Never in OneDrive or the kit.
