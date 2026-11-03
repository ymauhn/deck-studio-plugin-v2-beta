import pytest

from tests.helpers.kit_copy import make_kit_copy, remove_kit_copy


@pytest.fixture
def kit_copy():
    """A fresh plain copy of the kit, removed after the test."""
    root = make_kit_copy()
    yield root
    remove_kit_copy(root)
