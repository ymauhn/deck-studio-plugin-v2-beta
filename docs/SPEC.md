# Deck Studio v0: spec

Status: built (2026-10-28). No issue tracker is configured; this file is the spec of record for the user stories.
Date: 2026-10-27. Owner: Yeonatan Mauhnoom. Target deck: the NEXUS-GO defense deck kit.

> **Implementation note (2026-10-28).** The app was built in Python (FastAPI, uvicorn and the Claude Agent SDK for
> Python), not in Node, by the author's decision of 2026-10-27. Where this spec names Node pieces (node:http,
> the TypeScript SDK, node:test, Playwright Test), read their Python counterparts in `docs/PYTHON.md`, which wins
> where the two differ. The user stories and the HTTP contract stand.

## Problem Statement

The author is polishing a 45-slide HTML defense deck (plus 8 backup slides) nine days before the defense,
and must send a revised version to the advisors this week. The deck is built from hand-written HTML part
files by a build script, and a Beamer PDF and a narrated video are generated from it.

Today every change goes through the author's main Claude Code terminal session. The author has to describe
the slide and the box in words ("the second bullet on the data slide"), wait for the edit, rebuild, reopen
the browser, find the slide again and check. Each small edit lands in the same long conversation and fills
its context. There is no way to point at a box on the slide, no per-request undo, no place to drop a
reference article or image for the agent, and exporting or publishing needs commands. The author wants a
visual editor, like Canva or Wix but intelligent and aimed at academic and business presentations. It must
run locally and use the author's own Claude subscription, not API billing.

## Solution

Deck Studio is a small local web app. One command starts a server on 127.0.0.1 and opens the browser on a
three-pane screen:

- **Files** (left): the deck's slide sources, a `context/` folder and the skills folders. The author drags
  articles, notes, PDFs and images onto it, and they land in `context/`, where the agent can read them.
- **Deck** (center): the real deck, built in a studio mode in which every authored element carries its source
  location. In select mode the author hovers and clicks boxes. A click never changes the slide, and the
  selection becomes a chip in the chat (slide, element, source file and line). Double-clicking a plain text
  edits it in place.
- **Chat** (right): chats in tabs, each one its own Claude Code session run through the Claude Agent SDK on
  the author's subscription. A message carries the selection and an image of the slide. The agent:
  - edits only the allowed source files;
  - gets build errors back automatically;
  - checks its own result with a screenshot tool;
  - answers in Portuguese with a diff and an Undo button.

After any change the deck rebuilds (about 0.4 s) and reloads at the same slide and step.

Top-bar buttons export the PDF, publish the deck to its Netlify link (after an in-page confirmation) and
regenerate the Beamer version, each as a background job with a visible log. A usage meter shows the
subscription's 5-hour and weekly limits. A guard refuses to open a chat that would bill the API key.

## User Stories

### Opening and navigating

1. As the author, I want to start the studio with one command, so that I can edit without typing in a terminal session.
2. As the author, I want the browser to open on the studio automatically, so that I do not have to copy URLs.
3. As the author, I want to see my real deck exactly as it renders in the published version, so that what I edit is what I present.
4. As the author, I want the deck's own keys (arrows, space, number + G, N for notes, T for theme) to keep working inside the studio, so that I navigate the way I already know.
5. As the author, I want the studio to remember the slide and step I was on after any reload, so that I never lose my place.
6. As the author, I want to jump to a part file's first slide by clicking that file in the Files pane, so that I can find slides by section.

### Selecting boxes

7. As the author, I want a select mode that I toggle with a button and with the S key, so that clicking does not advance slides while I pick boxes.
8. As the author, I want a hover outline on the box under the pointer, so that I know what a click will select.
9. As the author, I want a click to select the box and show a chip with slide id, element type, source file and line, so that the agent knows exactly what I mean.
10. As the author, I want Shift+click to add more boxes to the selection, so that I can ask for a change across several elements.
11. As the author, I want Esc to clear the selection, so that I can start over quickly.
12. As the author, I want invisible things (fragments not yet revealed, masks at opacity 0) to be skipped by the picker, so that I select what I actually see.
13. As the author, I want a click inside a chart or diagram to select its component container and say which component renders it, so that the agent edits the component and not runtime DOM.
14. As the author, I want a click on a table to say that the table is generated from the dissertation and is read-only, so that I do not ask for impossible edits.
15. As the author, I want each selection to carry an image of the slide with the box outlined, so that the agent sees what I see.
16. As the author, I want picking to be paused while the deck is rebuilding, so that I never select a stale element.

### Chatting with the agent

17. As the author, I want to type a request in the chat and send it with Enter, so that asking for a change is as quick as describing it.
18. As the author, I want the answer to stream in as it is written, so that I know the agent is working.
19. As the author, I want compact cards for each file the agent read or edited, so that I can follow what it did without noise.
20. As the author, I want a diff of every request, so that I can review exactly what changed in the source.
21. As the author, I want an Undo button on every request, so that I can revert a bad change in one click.
22. As the author, I want several chats in tabs, each with its own session, so that unrelated tasks do not mix.
23. As the author, I want the studio's chats to stay out of my main Claude Code conversation and its resume list, so that my main context stays clean.
24. As the author, I want to choose the model per chat (Sonnet by default, Opus or Haiku when I want), so that small edits are fast and heavy design work gets the strongest model.
25. As the author, I want a Stop button for a running request, so that I can cut off a wrong direction.
26. As the author, I want my chats to survive a studio restart, so that I can continue a thread tomorrow.
27. As the author, I want a usage meter for the subscription's 5-hour and weekly limits, so that I do not run out before the defense.
28. As the author, I want the studio to refuse to open a chat that would use the API key instead of my subscription, and to say why, so that I am never billed by surprise.
29. As the author, I want the agent to follow the deck's rules on its own (numbers only from the dissertation or FACTS.md, English slide text, no em dashes, short bullets), so that I do not repeat them in every request.
30. As the author, I want the agent to look at a screenshot of the slide after it edits and fix overflow or overlap before it answers, so that I get a slide that already fits.
31. As the author, I want the agent to answer me in Brazilian Portuguese, so that the conversation is in my language.
32. As the author, I want the agent to build new elements and new slides with the deck's own grid, classes and components, so that new material looks like the rest of the deck.
33. As the author, I want the agent to use my existing Claude Code skills and to create new skills when I ask, so that the studio grows with my workflow.
34. As the author, I want an approval card for anything outside the allowed area (shell commands, web access, files outside the deck sources), so that I stay in control.
35. As the author, I want the agent to be unable to change the dissertation sources, the data folder or generated files, so that the deck's sources of truth stay intact.
36. As the author, I want only one request to edit files at a time, with the others waiting their turn, so that two chats never overwrite each other.
37. As the author, I want build errors to be sent back to the agent automatically, so that it fixes them in the same request.
38. As the author, I want the chat to tell me when a request ended with an error or was stopped, so that I know the state of my files.

### Editing text directly

39. As the author, I want to double-click a plain text box and edit it in place, so that typo fixes need no agent.
40. As the author, I want Enter to save and Esc to cancel an in-place edit, so that editing feels like any text field.
41. As the author, I want an in-place edit to change only that text in the source file, keeping its formatting and line endings, so that the source stays clean.
42. As the author, I want in-place editing to be refused on generated content (tables, math, component internals), with a short reason, so that I use the chat for those.
43. As the author, I want an in-place edit to be refused if the source changed since I selected the box, so that I never overwrite newer text.
44. As the author, I want to undo an in-place edit, so that a slip is easy to revert.

### Files and context

45. As the author, I want a Files pane listing the slide sources, the context folder and the skills folders, so that I see what the agent can use.
46. As the author, I want to drag and drop files onto the Files pane and have them saved in the context folder, so that the agent can use them as reference.
47. As the author, I want a dropped file never to overwrite an existing one, so that I do not lose material.
48. As the author, I want the agent to read PDFs, Markdown, LaTeX and images from the context folder, so that it can quote the article or follow a reference image.
49. As the author, I want the agent to place a dropped image on a slide, so that new figures get into the deck without manual copying.

### Outputs

50. As the author, I want an Export PDF button that builds a clean deck and writes the PDF, with progress and the output path, so that I can send it to the advisors.
51. As the author, I want a Publish button that asks for confirmation and then updates the deck's Netlify link, so that the advisors always see the latest version at the same URL.
52. As the author, I want a Regenerate Beamer button that runs in the background with a log and a final status, so that the Beamer PDF follows the HTML.
53. As the author, I want exports and publishing to use the clean build without studio markers, so that what I send is identical to the normal deck.

### Safety and housekeeping

54. As the author, I want the studio reachable only from my own machine, behind a per-launch secret, so that nobody else can drive an agent that edits my files.
55. As the author, I want other web pages open in my browser to be unable to send commands to the studio, so that a malicious page cannot use it.
56. As the author, I want the studio's own data (history, chats) outside OneDrive, so that sync does not fight with it.
57. As the author, I want the studio's tests never to touch my real deck kit or publish anything, so that development is safe.
58. As a future user of the studio with another deck, I want the deck-specific parts (paths, build commands, rules) in one adapter configuration, so that the studio can be pointed at a different deck later.

## Implementation Decisions

### Shape

- A separate project folder outside OneDrive. The NEXUS-GO deck kit is a configured target, not part of the app.
- Python 3.12 with FastAPI and uvicorn: Server-Sent Events from server to browser, JSON POSTs from browser to server. (First drafted for Node 24; see the note at the top.)
- Browser UI in plain HTML, CSS and JavaScript modules, styled with the deck's tokens (palette and fonts). UI strings in Brazilian Portuguese.
- Runtime dependencies are kept to a minimum and pinned in `pyproject.toml`: the Claude Agent SDK for Python (0.2.174, which bundles the CLI 2.1.310), PyMuPDF for the Beamer pages, and Playwright for screenshots. The kit's own build keeps parse5 for HTML source locations. The test-only dependencies are pytest and pytest-playwright.
- App data (history snapshots, chat registry, logs) lives in the user's local app-data folder, not in the kit and not in OneDrive.

### Deep modules

1. **Deck adapter.** This is the only place that knows the target deck. Its configuration is:
   - the kit root;
   - the slide sources folder;
   - the studio build command and its output path;
   - the clean build command;
   - the context folder and the user images folder;
   - the write policy lists;
   - the job commands.

   Its operations are: build the studio deck, build the clean deck, list part files with their slide ids, run a named job.

   On the kit side, the deck's build script gains a studio mode:
   - **Locations.** Every authored element inside a slide gets a `data-loc` attribute holding the part file, line and column. It comes from an HTML parser with source locations.
   - **Generated nodes.** The three build rewrites that match exact markup (inline math, display math, the table placeholder) accept the extra attribute and carry it to the nodes they generate.
   - **Output and images.** The output goes to a studio path, never to the published dist file. User images placed in a source images folder are inlined exactly like the existing processed images.

   The normal build must stay byte-identical to the current one. The spike measured this mapping: 1044 of 1044 annotated elements resolved to the right source element, 16 of 16 picked targets were correct, and the build cost was +23 ms.
2. **Source editor** (pure). It resolves a location to its element, with start and end offsets, and replaces one text node by child index:
   - **Stale check:** the current text must equal the text the browser saw.
   - **Encoding:** the new text is HTML-escaped. Text nodes that contain entities are refused.
   - **Format:** the file's own line endings are kept.

   It returns the new content and a unified diff. The kit mixes LF and CRLF part files.
3. **Write guard** (pure). It classifies a tool call or a path as allow, deny (with a reason) or ask. Paths are normalized for Windows: backslashes, drive-letter case and `..` traversal.
   - **Allowed:** writes in the slide sources tree, the context folder and the project skills folder.
   - **Denied:**
     - the dissertation sources and the data folder;
     - the generated Beamer source, the dist and build outputs;
     - anything outside the kit except the user skills folder.
   - **Asked:** the user skills folder, shell commands, web access and any write not covered above.
4. **History.** Before the first write to a file within a turn, it snapshots the file's content (or that the file did not exist). It also stores the after-content when the turn ends.
   - **Undo:** restores the before-content of every file the turn touched.
   - **Refusal:** if a file changed after the turn, undo is refused with a conflict, so the user undoes newer turns first.
   - **Coverage:** in-place edits are turns of their own. Shell commands are not covered, and the approval card says so.
5. **Agent session.** A wrapper over the SDK's `query` with an injectable implementation, so tests run a scripted fake with the same contract. Each chat is one long-lived query fed by an async message queue (streaming input), which allows image blocks, interrupt and model changes. Fixed options:
   - **Environment:**
     - a copy of the process environment with every `ANTHROPIC_*` and `CLAUDE*` variable removed;
     - auto memory and claude.ai connectors switched off;
     - user hooks disabled for these sessions (SDK hook callbacks still fire).
   - **Auth gate:** on the init message the source of the API key must be `none` and the account must be on a subscription, otherwise the chat is closed with an explanatory error.
   - **Context and tools:**
     - setting sources: user and project, which load CLAUDE.md files and the skills;
     - a strict MCP configuration with only the in-process deck tools.
   - **Permissions and model:**
     - the permission mode is set explicitly to default, because the user's settings default to auto;
     - the model is chosen per chat;
     - the system prompt is the Claude Code preset plus a studio appendix: scope of the selection, deck rules, answer in Portuguese, verify with a screenshot.
   - **Streaming and sessions:** partial messages are streamed. Sessions persist and are resumed by id, never with "continue".

   Policy and approvals run in a PreToolUse hook callback, which awaits the user's decision for ask cases. The permission callback is not used for this, because allowed tools and the user's allow rules bypass it. A PostToolUse hook on writes inside the slide sources triggers a rebuild, and build errors go back to the agent as additional context.
6. **Deck tools** (in-process MCP server named `deck`):
   - `get_selection` returns the current selection;
   - `screenshot_slide(slide, step?, highlightLoc?)` returns a PNG image;
   - `check_slide(slide, step?)` reports text boxes whose content overflows them and elements outside the slide frame;
   - `rebuild_deck` runs the studio build and reports errors;
   - `add_image(contextFile, name?)` copies an image from the context folder into the user images folder and returns the reference to use in the HTML.
7. **Renderer.** A persistent headless Chromium page with the studio deck, used for screenshots and checks. It reloads after each build.
8. **Server.** Routes, security, the event hub, the turn lock (one running turn across all chats; others get 409 Busy and the UI waits), the chat registry and the job runner.
9. **UI.** Three panes. The deck runs in a same-origin iframe, and the picker is injected into the deck page only in studio mode. It also holds the chat tabs, approvals, jobs and the usage meter.

### HTTP contract (decision of record)

- **Security:**
  - Bind to 127.0.0.1 only. A random token is created at launch, and the launch URL is `/?t=<token>`. Loading it sets an HttpOnly, SameSite=Strict cookie and redirects to `/`.
  - Every other route requires the cookie, or an `x-studio-token` header for tests.
  - The `Host` header must be `127.0.0.1:<port>` or `localhost:<port>`. POSTs must have an `Origin` equal to the studio's own origin; header-token clients are exempt.
- **Routes:**
  - `GET /`, `GET /ui/*`: the studio UI.
  - `GET /deck`: the studio deck with the picker injected.
  - `GET /api/status`: auth state, build state, busy flag, usage.
  - `GET /api/files?dir=`: entries of an allowed root.
  - `POST /api/files/upload`: raw body with the file name in a header. Saves into the context folder, never overwrites, size limit 50 MB.
  - `GET /api/chats`, `POST /api/chats` (`{model?}`).
  - `POST /api/chats/:id/messages` (`{text, selection?: Selection[]}`): returns `{turnId}`, or 409 when busy.
  - `POST /api/chats/:id/interrupt`.
  - `POST /api/chats/:id/model` (`{model}`).
  - `POST /api/approvals/:id` (`{decision: "allow" | "deny"}`).
  - `GET /api/turns/:id/diff`.
  - `POST /api/turns/:id/undo`: 409 on conflict.
  - `POST /api/edit-text` (`{loc, childIndex, oldText, newText}`): 409 when stale, 422 when not editable.
  - `POST /api/jobs/:name` (`export-pdf`, `publish` (requires `{confirm: true}`), `beamer`).
  - `GET /api/events`: an SSE stream.
- **Events** (`data: {type, ...}`):
  - `status`;
  - `build` (running, ok or error, with the error text and ms);
  - `deck-reload`;
  - `chat` (user, text-delta, text, tool, result, error and turn-end, each with chatId and turnId);
  - `approval` (id, chatId, tool, summary);
  - `job` (id, name, state, log line).
- **Selection** (sent by the picker, stored by the server, returned by `get_selection`):
  ```
  { slideId: "s13", slide: 13, step: 3, part: "03-data.html",
    loc: { file: "deck/src/slides/03-data.html", line: 9, col: 5 },
    tag: "li", classes: ["f"], text: "...", outerHTML: "... (at most 2000 chars)",
    kind: "text" | "component" | "table" | "math" | "figure" | "element",
    component: "INT-PIPE" (when kind is component), rect: { x, y, w, h } }
  ```

### Other decisions

- **Reload.** In v0, every change does a full studio rebuild, then the iframe reloads and the server restores the slide and step through the deck's `window.deck.go(n, step)`. The spike measured 1.2 s from edit to screen. Swapping a single slide in place (0.5 s) needs an engine change and comes later.
- **Default model.** Sonnet for new chats, with Opus and Haiku available.
- **Undo.** The app keeps its own snapshots instead of the SDK's file checkpointing, because the same store must cover in-place edits and agent edits.
- **Fake agent.** The fake used by tests is driven by scenario files. A marker in the message text picks the scenario.
  - **Step types:** say text, call a tool with input, request approval, fail, report usage.
  - **Faithfulness:** the fake calls the session's real PreToolUse and PostToolUse callbacks and performs Edit and Write itself, so the guard, history, rebuild and reload paths are the real ones.
- **Jobs.** Export PDF runs the clean build and then the kit's PDF exporter. Publish runs the clean build and then the kit's Netlify publish script; it is outward-facing, so it requires `confirm: true`, which the UI sends only after an in-page confirmation. Beamer runs the kit's Beamer build. The job commands come from the adapter configuration, so tests replace them with harmless commands.

## Testing Decisions

- **Seams.** A good test exercises external behavior through a public seam and never reaches into private functions. Tests must be deterministic and must never touch the real kit, the network or the real Netlify site.
  1. **Browser and HTTP (primary).** pytest-playwright drives the real UI against a server started on a random port. The server uses a disposable plain copy of the kit (the deck folder with its node_modules and build caches, the tools and data folders, and the dissertation .tex; about 3 s to make) and the fake agent. Every user story about selecting, chatting, editing, undoing, uploading, approvals and jobs is verified here.
  2. **The SDK boundary.** It is a substitution seam, not a test target: the agent session takes its `query` implementation as a parameter. One opt-in live smoke test (`STUDIO_LIVE=1`) runs the real SDK against a kit copy. It checks the subscription auth gate, a read-only answer, that the guard hook blocks a write to the data folder, and that an allowed edit triggers a rebuild. It uses a small amount of the subscription, so it is run by hand.
  3. **Safety-critical pure modules.** The source editor, the write guard and history get pytest tests through their public functions, because they encode rules whose failure loses data: stale edits, line endings, entities, Windows path traversal, undo conflicts.
  4. **The deck adapter's studio build.** It is tested on a kit copy. Every `data-loc` resolves to an element with the same tag and classes in the source (expected 100%). The clean build's output hash is unchanged by the new code. All equations still render, and tables keep their location.
- **TDD.** Work proceeds in vertical slices with red-green-refactor. Each slice starts with one failing Playwright or module test that states the behavior, then the minimum code to pass, then a refactor.
- **Prior art:**
  - the kit's Python Playwright QA (the deck checks and the component tests);
  - the 2026-10-27 spikes: the mapping checks over all elements, the pick script and the edit-and-reload loop timing.

## Out of Scope

- Interactive Beamer mode: the PDF.js view, SyncTeX at frame level with text matching, and the geometric mapping from PDF clicks to HTML elements. The design is recorded and comes after the defense.
- Swapping a single slide in place without reloading the page.
- Drag and resize of boxes on the 12-column grid, comment batches across slides, and provenance chips for numbers.
- Editing generated tables in place; their source is the dissertation, which is read-only.
- Access from other machines, sharing the studio with other people, and any distribution. Distributing the app would require API-key auth by Anthropic policy.
- PPTX export, Typst, a mobile layout, and git integration.

## Further Notes

- **Policy.** Running this personal tool on the author's own machine with the author's own Claude Code login is the use Anthropic describes for the Agent SDK on a plan. Its support article updated on 2026-10-07 says SDK and `claude -p` usage draw from the subscription limits. Offering that login to other people is not allowed. The policy changed four times in 2026, so the auth gate runs on every chat.
- **Measurements on this PC (spikes of 2026-10-27):**
  - the SDK on the Max plan: `apiKeySource: none`;
  - opening a chat takes 1.1 s with the lean configuration, against 8.2 s with every MCP server (about 325k tokens of context);
  - a warm reply starts in about 3 s on Opus;
  - the deck build takes 0.4 s, and an edit reaches the screen in 1.2 s with a full reload;
  - the full Beamer takes 33 to 35 s per pass, and one frame takes 1.5 s per pass.
- **Glossary:**
  - **part file:** one HTML source file holding several slides;
  - **slide id:** `sNN`, the section id;
  - **step:** a fragment index within a slide;
  - **component:** an `INT-*` runtime-rendered diagram or chart;
  - **studio deck:** the build with `data-loc` markers;
  - **clean deck:** the normal build;
  - **turn:** one request, or one in-place edit, and the file changes it made;
  - **context folder:** where dropped reference files go.
- **Timeline:** the defense is on 2026-11-05, and v0 is needed today, 2026-10-27, so that revisions reach the advisors this week.
