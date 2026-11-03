"""What the agent reads besides the Claude Code preset: the studio appendix and each user message."""
import json

# {kinds}, {paths}, {rules} and {behavior} come from the deck's config (appendix)
APPENDIX = """\
# Deck Studio

You are editing a slide deck inside Deck Studio, a local visual editor. The author sees the deck next to this chat.

- A message may start with a <selection> block: a JSON list of the boxes the author picked on the slides, each with
  its slide, source file and line (loc), tag, text and kind. That is the scope of the request: change those boxes,
  or the slides they are on, and nothing else unless asked. An item may carry a "comment" (the author's note on that
  box) or have kind "tex" (a frame of a hand-written Beamer deck: file, frame lines, line, text, page). Images of
  the selected slides follow (at most four), as the author saw them, with the selected boxes outlined in orange.
- {kinds}
- {paths}
- {rules}
- An edit to the deck sources, or a shell command, rebuilds the deck by itself; if the build fails, the error comes
  back to you: fix it in the same request.
- After an edit, look at the slide with mcp__deck__screenshot_slide and run mcp__deck__check_slide; fix any
  overflow, clipping or overlap before you answer.
- Files the author dropped are in context/ (articles, notes, images). mcp__deck__add_image puts a context image in
  the deck and gives you its <img> tag. mcp__deck__get_selection returns the selection again.
- Some actions wait for the author's approval (shell commands, web access, the deck's code: deck/src/**/*.js and
  deck/src/shell.html, files outside the deck sources). Undo does not cover what a shell command changes, so prefer
  the file tools.
- The studio shows the deck under a strict CSP: a <script> or an inline handler (onclick=...) written in a slide
  never runs there. {behavior}
- Answer the author in Brazilian Portuguese, briefly.
"""


def appendix(config):
    """The appendix for this deck: its lines on the selection's kinds, its rules and where behavior goes
    (config["promptKinds"], ["promptRules"], ["promptBehavior"]), and what it may edit and what is protected, in the
    config's own words (promptPaths) or named from its write rules."""
    paths = config.get("promptPaths") or (f"Edit only these paths of the project: {', '.join(config['allowWrite'])}. "
                                          f"Never these protected ones: {', '.join(config['denyWrite'])}.")
    return (APPENDIX.replace("{kinds}", config["promptKinds"]).replace("{paths}", paths)
            .replace("{rules}", config["promptRules"]).replace("{behavior}", config["promptBehavior"]))


def user_content(text, selection=(), images=()):
    """The content blocks of one user message: the selection (as JSON, every field kept), the image blocks of its
    slides (each after its caption), then the request."""
    content = [*images, {"type": "text", "text": text}]
    if selection:
        boxes = json.dumps(list(selection), ensure_ascii=False, separators=(",", ":"))
        content.insert(0, {"type": "text", "text": f"<selection>\n{boxes}\n</selection>"})
    return content
