import pytest

import cacheroute.compat.runtime as canonical_runtime
import cacheroute_compat.runtime as legacy_runtime
import core.runtime_compat as core_runtime

filter_supported_keys = canonical_runtime.filter_supported_keys
normalize_runtime_profile = canonical_runtime.normalize_runtime_profile
resolve_scan_match = canonical_runtime.resolve_scan_match


def test_legacy_import_forwards_to_canonical_objects():
    assert legacy_runtime.__all__ == canonical_runtime.__all__
    assert core_runtime.__all__ == canonical_runtime.__all__
    for name in canonical_runtime.__all__:
        canonical = getattr(canonical_runtime, name)
        assert getattr(legacy_runtime, name) is canonical
        assert getattr(core_runtime, name) is canonical


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
