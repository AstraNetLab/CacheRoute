import pytest

from core.runtime_compat import normalize_runtime_profile


@pytest.mark.parametrize("value, expected", [
    ("old", "legacy"), ("v0", "legacy"), ("modern", "v1"),
    ("new", "v1"), ("current", "v1"), ("mock", "test/mock"),
    ("test", "test/mock"),
])
def test_runtime_profile_aliases(value, expected):
    assert normalize_runtime_profile(value) == expected


def test_invalid_runtime_profile():
    with pytest.raises(ValueError):
        normalize_runtime_profile("unsupported")
