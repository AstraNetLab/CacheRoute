import pytest

from core.runtime_compat import filter_supported_keys, normalize_runtime_profile, resolve_scan_match


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


def test_mock_profile_never_selects_real_redis_keys():
    with pytest.raises(ValueError, match="real Redis"):
        resolve_scan_match("test/mock", None)
    with pytest.raises(ValueError, match="real Redis"):
        filter_supported_keys({b"vllm@legacy", b"model@x@y@" + b"a" * 32}, "test/mock", None)
