"""The settings panel: the model of new chats and the skills catalog (PYTHON.md "Skills"; SPEC story 33).

The studio runs with a stand-in home folder (USERPROFILE), so the catalog never lists the real ~/.claude."""
import json

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import run_studio
from tests.helpers.kit_copy import make_kit_copy, remove_kit_copy


def skill(folder):
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(f"---\nname: {folder.name}\ndescription: test skill\n---\n", encoding="utf-8")


@pytest.fixture(scope="module")
def home(tmp_path_factory):
    """User skills humanizer, thesis-review and scratch-notes; plugins frontend-design, impeccable and toolbox."""
    home = tmp_path_factory.mktemp("home")
    for name in ["humanizer", "thesis-review", "scratch-notes"]:
        skill(home / ".claude" / "skills" / name)
    plugins = {}
    for plugin, names in {"frontend-design": ["frontend-design"], "impeccable": ["impeccable"],
                          "toolbox": ["alpha", "beta"]}.items():
        for name in names:
            skill(home / "plugins" / plugin / "skills" / name)
        plugins[f"{plugin}@market"] = [{"scope": "user", "installPath": str(home / "plugins" / plugin)}]
    registry = home / ".claude" / "plugins" / "installed_plugins.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"version": 2, "plugins": plugins}), encoding="utf-8")
    return home


@pytest.fixture(scope="module")
def studio(home):
    kit = make_kit_copy()
    skill(kit / ".claude" / "skills" / "deck-notes")  # a project skill
    try:
        with run_studio(kit=kit, env={"USERPROFILE": str(home)}) as s:
            yield s
    finally:
        remove_kit_copy(kit)


def composer(page):
    return page.get_by_role("textbox", name="Mensagem")


def answers(page):
    return page.get_by_role("log", name="Conversa").get_by_role("article", name="Claude")


def send(page, text):
    composer(page).fill(text)
    composer(page).press("Enter")


def new_chat(page):
    """Open a new chat tab and wait until it is the current one."""
    tabs = page.get_by_role("tablist", name="Chats").get_by_role("tab")
    n = tabs.count()
    page.get_by_role("button", name="Novo chat").click()
    expect(tabs).to_have_count(n + 1)
    expect(tabs.last).to_have_attribute("aria-selected", "true")


def open_settings(page):
    page.get_by_role("button", name="Configurações").click()
    dialog = page.get_by_role("dialog", name="Configurações")
    expect(dialog).to_be_visible()
    return dialog


def test_new_chats_take_the_default_model_of_the_settings_and_open_chats_keep_theirs(studio, studio_page, api):
    page = studio_page
    model = page.get_by_role("combobox", name="Modelo", exact=True)
    expect(model).to_have_value("opus")
    dialog = open_settings(page)
    default = dialog.get_by_role("combobox", name="Modelo dos chats novos")
    expect(default).to_have_value("opus")
    default.select_option(label="Sonnet")
    dialog.get_by_role("button", name="Salvar").click()
    expect(dialog).to_be_hidden()
    expect(model).to_have_value("opus")

    new_chat(page)
    expect(model).to_have_value("sonnet")
    send(page, "#scenario:model")
    expect(answers(page)).to_have_text(["Modelo: sonnet"])

    page.reload()
    expect(open_settings(page).get_by_role("combobox", name="Modelo dos chats novos")).to_have_value("sonnet")
    assert api.get(f"{studio.base}/api/settings", headers=studio.headers).json()["model"] == "sonnet"


DEFAULTS = {"deck-notes", "frontend-design:frontend-design", "impeccable:impeccable", "dataviz",
            "deck-studio-skills:humanizer", "deck-studio-skills:thesis-review"}  # docs/PYTHON.md "Skills"


def init_skills(page, text="#scenario:hello"):
    """Send a message: the skills its session runs with, from that turn's init event."""
    page.evaluate("""() => { window.init = new Promise((resolve) => {
        const off = studio.on('chat', (e) => { if (e.kind === 'init') { off(); resolve(e.skills); } });
    }); }""")
    send(page, text)
    return set(page.evaluate("() => window.init"))


def test_the_skills_start_from_the_default_set_and_a_change_applies_to_the_chats_opened_after_it(studio, studio_page):
    page = studio_page
    assert init_skills(page) == DEFAULTS  # this chat's session opens now

    dialog = open_settings(page)
    box = lambda name: dialog.get_by_role("checkbox", name=name, exact=True)  # noqa: E731
    for name in ["deck-notes", "humanizer", "thesis-review", "frontend-design", "impeccable", "dataviz"]:
        expect(box(name)).to_be_checked()
    for name in ["scratch-notes", "deep-research"]:
        expect(box(name)).not_to_be_checked()
    expect(box("alpha")).to_be_hidden()  # a plugin without a selected skill starts folded
    dialog.locator("summary", has_text="toolbox").click()
    expect(box("alpha")).not_to_be_checked()
    box("alpha").check()
    box("humanizer").uncheck()
    dialog.get_by_role("button", name="Salvar").click()
    expect(dialog).to_be_hidden()

    chosen = DEFAULTS - {"deck-studio-skills:humanizer"} | {"toolbox:alpha"}
    assert init_skills(page) == DEFAULTS  # the open chat keeps its session
    new_chat(page)
    assert init_skills(page) == chosen

    skill(studio.kit / ".claude" / "skills" / "made-in-chat")  # a project skill made later is on, as by default
    new_chat(page)
    assert init_skills(page) == chosen | {"made-in-chat"}

    page.reload()
    dialog = open_settings(page)
    expect(box("humanizer")).not_to_be_checked()
    expect(box("alpha")).to_be_checked()
