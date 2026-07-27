from core.runtime_compat import (
    classify_lmcache_redis_key,
    filter_supported_keys,
    normalize_runtime_profile,
    resolve_scan_match,
)


def test_profile_aliases():
    assert normalize_runtime_profile("old") == "legacy"
    assert normalize_runtime_profile("modern") == "v1"


def test_historic_default_match_is_profile_aware():
    assert resolve_scan_match("auto", "vllm@*") == "*"
    assert resolve_scan_match("v1", "vllm@*") == "*"
    assert resolve_scan_match("legacy", "vllm@*") == "vllm@*"


def test_classifies_legacy_and_v1_keys():
    legacy = b"vllm@0123456789abcdef"
    modern = (
        b"/workspace/llm-stack/models/Meta-Llama-3-70B-Instruct"
        b"@08000800@@d51d1eac7122c3b998e188f97d30caedd7a4dcfad7d5c91187097efee4eaf9d0"
    )
    assert classify_lmcache_redis_key(legacy) == "legacy"
    assert classify_lmcache_redis_key(modern) == "v1"
    assert classify_lmcache_redis_key(b"unrelated") is None


def test_auto_filter_keeps_both_generations():
    legacy = b"vllm@0123456789abcdef"
    modern = b"/model@1@0@" + b"a" * 64 + b"@bfloat16"
    unrelated = b"healthcheck"
    assert filter_supported_keys(
        {legacy, modern, unrelated},
        profile="auto",
        requested_match="auto",
    ) == {legacy, modern}
