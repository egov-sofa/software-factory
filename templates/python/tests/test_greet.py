import pytest

from {{PACKAGE_NAME}} import greet


def test_greets_a_person_by_name():
    assert greet("Ada") == "Hello, Ada!"


def test_trims_surrounding_whitespace():
    assert greet("  Ada  ") == "Hello, Ada!"


def test_rejects_an_empty_name():
    with pytest.raises(ValueError, match="name must not be empty"):
        greet("   ")
