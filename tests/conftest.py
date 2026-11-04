import shutil

import pytest

from tests.helpers.kit_copy import make_kit_copy, remove_kit_copy

# these compile Beamer decks: without TeX on the machine (the CI runners) they skip
TEX_MODULES = {"test_beamer.py", "test_beamer_project.py", "test_beamer_engine.py", "test_beamer_perl.py"}


def pytest_collection_modifyitems(config, items):
    if shutil.which("pdflatex"):
        return
    skip = pytest.mark.skip(reason="needs TeX (pdflatex) on the machine")
    for item in items:
        if item.path.name in TEX_MODULES or "pdflatex" in item.name:
            item.add_marker(skip)


@pytest.fixture
def kit_copy():
    """A fresh plain copy of the kit, removed after the test."""
    root = make_kit_copy()
    yield root
    remove_kit_copy(root)
