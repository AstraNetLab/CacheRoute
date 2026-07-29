#!/usr/bin/env python3
"""Build, inspect, inject, and consume CacheRoute v1 KDN artifacts.

The subcommands are deliberately staged because a reliable L2-consumption test
requires LMCache and vLLM to be restarted after Redis restore, clearing L1/GPU
state before ``consume``.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
for source_root in (REPO_ROOT, REPO_ROOT / "src"):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

import redis  # noqa: E402

from kdn_server.kv_injector import KVCacheInjector  # noqa: E402
from kdn_server.text_db import _normalize_text, compute_kid  # noqa: E402

VLLM_METRICS = (
    "vllm:external_prefix_cache_queries_total",
    "vllm:external_prefix_cache_hits_total",
    "vllm:prompt_tokens_cached_total",
    "vllm:prompt_tokens_total",
)
LMCACHE_METRICS = (
    "lmcache_mp_lookup_requested_tokens_total",
    "lmcache_mp_lookup_hit_tokens_total",
    "lmcache_mp_l2_prefetch_lookup_requests_total",
    "lmcache_mp_l2_prefetch_lookup_objects_chunks_total",
    "lmcache_mp_l2_prefetch_hit_chunks_total",
    "lmcache_mp_l2_prefetch_load_submitted_requests_total",
    "lmcache_mp_l2_prefetch_load_submitted_objects_chunks_total",
    "lmcache_mp_l2_prefetch_load_completed_chunks_total",
    "lmcache_mp_l2_load_completed_requests_total",
    "lmcache_mp_l2_prefetch_failure_chunks_total",
    "lmcache_mp_l1_read_chunks_total",
    "lmcache_mp_l1_write_chunks_total",
)


@dataclass(frozen=True)
class ManifestRecord:
    key: bytes
    file: Path
    size: int


def http_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "CacheRoute-v1-validator"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"HTTP {response.status}: {body[:1000]}")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body[:1000]}") from exc
    value = json.loads(body)
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object from {url}, got {type(value).__name__}")
    return value


def http_text(url: str, timeout: float = 20.0) -> str:
    request = Request(url, headers={"User-Agent": "CacheRoute-v1-validator"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def document_identity(path: Path) -> tuple[str, str]:
    raw = path.read_text(encoding="utf-8")
    normalized = _normalize_text(raw)
    if not normalized:
        raise ValueError(f"document is empty after normalization: {path}")
    return normalized, compute_kid(normalized)


def decode_key(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def load_manifest(kv_dir: Path) -> list[ManifestRecord]:
    manifest = kv_dir / "manifest.jsonl"
    if not manifest.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest}")
    records: list[ManifestRecord] = []
    with manifest.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            key_b64 = value.get("key_b64url")
            rel_file = value.get("file")
            size = value.get("bytes")
            if not isinstance(key_b64, str) or not isinstance(rel_file, str):
                raise ValueError(f"invalid manifest record at line {line_no}: {value}")
            file_path = kv_dir / rel_file
            if not file_path.is_file():
                raise FileNotFoundError(f"missing dump at line {line_no}: {file_path}")
            actual_size = file_path.stat().st_size
            expected_size = int(size) if size is not None else actual_size
            if actual_size != expected_size:
                raise ValueError(
                    f"dump size mismatch at line {line_no}: expected={expected_size} actual={actual_size}"
                )
            records.append(ManifestRecord(decode_key(key_b64), file_path, expected_size))
    if not records:
        raise ValueError(f"manifest has no records: {manifest}")
    return records


def resolve_artifact(document: Path, kv_root: Path) -> tuple[str, str, Path, list[ManifestRecord]]:
    normalized, kid = document_identity(document)
    kv_dir = kv_root / kid
    records = load_manifest(kv_dir)
    return normalized, kid, kv_dir, records


def print_json(title: str, value: dict[str, Any]) -> None:
    print(f"\n===== {title} =====")
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def inspect_artifact(document: Path, kv_root: Path) -> dict[str, Any]:
    normalized, kid, kv_dir, records = resolve_artifact(document, kv_root)
    run_meta_path = kv_dir / "run_meta.json"
    run_meta = json.loads(run_meta_path.read_text(encoding="utf-8")) if run_meta_path.is_file() else {}
    dump_files = list((kv_dir / "blocks").glob("*.dump"))
    payload_bytes = sum(record.size for record in records)
    errors: list[str] = []

    if len(dump_files) != len(records):
        errors.append(f"manifest records={len(records)} but dump files={len(dump_files)}")
    if run_meta:
        if int(run_meta.get("dumped_keys", -1)) != len(records):
            errors.append(
                f"run_meta dumped_keys={run_meta.get('dumped_keys')} but manifest={len(records)}"
            )
        if run_meta.get("runtime_profile") != "v1":
            errors.append(f"run_meta runtime_profile={run_meta.get('runtime_profile')!r}, expected 'v1'")
        if "v1" not in (run_meta.get("key_formats") or []):
            errors.append(f"run_meta key_formats={run_meta.get('key_formats')!r} lacks 'v1'")

    result = {
        "ok": not errors,
        "document": str(document),
        "document_bytes": document.stat().st_size,
        "normalized_characters": len(normalized),
        "kid": kid,
        "kv_dir": str(kv_dir),
        "manifest_records": len(records),
        "dump_files": len(dump_files),
        "payload_bytes": payload_bytes,
        "run_meta": run_meta,
        "errors": errors,
    }
    print_json("ARTIFACT INSPECTION", result)
    if errors:
        raise RuntimeError("artifact inspection failed")
    return result


def redis_client(args: argparse.Namespace) -> redis.Redis:
    return redis.Redis(
        host=args.redis_host,
        port=args.redis_port,
        db=args.redis_db,
        password=args.redis_password,
        decode_responses=False,
        socket_connect_timeout=5,
        socket_timeout=120,
    )


def sample_indices(length: int, count: int) -> list[int]:
    if count <= 0 or length <= 0:
        return []
    if count >= length:
        return list(range(length))
    if count == 1:
        return [0]
    return sorted({round(index * (length - 1) / (count - 1)) for index in range(count)})


def inject_artifact(args: argparse.Namespace) -> dict[str, Any]:
    _, kid, kv_dir, records = resolve_artifact(args.document, args.kv_root)
    client = redis_client(args)
    if not client.ping():
        raise RuntimeError("Redis ping failed")
    before_size = int(client.dbsize())

    if args.flush_redis:
        if not args.yes:
            raise RuntimeError("--flush-redis requires --yes because it deletes the entire selected DB")
        client.flushdb()
    elif before_size and not args.allow_extra_keys:
        raise RuntimeError(
            f"Redis DB contains {before_size} keys; use an empty DB, --flush-redis --yes, "
            "or explicitly allow extras with --allow-extra-keys"
        )

    injector = KVCacheInjector(
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        redis_db=args.redis_db,
        redis_password=args.redis_password,
        socket_timeout_s=120,
    )
    started = time.perf_counter()
    injected = injector.inject_kv_dir(str(kv_dir), return_keys=False)
    elapsed = time.perf_counter() - started

    expected_keys = {record.key for record in records}
    actual_keys = set(client.scan_iter(match=b"*", count=1000))
    missing_keys = expected_keys - actual_keys
    extra_keys = actual_keys - expected_keys
    size_mismatches: list[dict[str, Any]] = []
    actual_payload_bytes = 0
    for record in records:
        if record.key not in actual_keys:
            continue
        actual_size = int(client.strlen(record.key))
        actual_payload_bytes += actual_size
        if actual_size != record.size:
            size_mismatches.append(
                {"key": repr(record.key), "expected": record.size, "actual": actual_size}
            )

    hash_checks: list[dict[str, Any]] = []
    for index in sample_indices(len(records), args.sample_hashes):
        record = records[index]
        expected = record.file.read_bytes()
        actual = client.get(record.key)
        hash_checks.append(
            {
                "index": index,
                "bytes": record.size,
                "match": actual is not None
                and hashlib.sha256(expected).digest() == hashlib.sha256(actual).digest(),
            }
        )

    expected_payload_bytes = sum(record.size for record in records)
    ok = (
        injected.injected == len(records)
        and injected.missing_files == 0
        and not missing_keys
        and (args.allow_extra_keys or not extra_keys)
        and not size_mismatches
        and actual_payload_bytes == expected_payload_bytes
        and all(item["match"] for item in hash_checks)
    )
    result = {
        "ok": ok,
        "kid": kid,
        "redis": f"{args.redis_host}:{args.redis_port}/{args.redis_db}",
        "dbsize_before": before_size,
        "dbsize_after": int(client.dbsize()),
        "injected": injected.injected,
        "missing_files": injected.missing_files,
        "manifest_records": len(records),
        "missing_keys": len(missing_keys),
        "extra_keys": len(extra_keys),
        "size_mismatches": size_mismatches,
        "expected_payload_bytes": expected_payload_bytes,
        "actual_payload_bytes": actual_payload_bytes,
        "sample_sha256": hash_checks,
        "elapsed_seconds": round(elapsed, 3),
    }
    print_json("REDIS INJECTION", result)
    if not ok:
        raise RuntimeError("Redis injection verification failed")
    return result


def parse_prometheus(text: str, names: Iterable[str]) -> dict[str, float]:
    result = {name: 0.0 for name in names}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        for name in result:
            if line.startswith(name + "{") or line.startswith(name + " "):
                try:
                    result[name] += float(line.rsplit(None, 1)[1])
                except (IndexError, ValueError):
                    pass
                break
    return result


def metric_delta(before: dict[str, float], after: dict[str, float]) -> dict[str, float]:
    return {name: after[name] - before[name] for name in before}


def consume_artifact(args: argparse.Namespace) -> dict[str, Any]:
    normalized, kid, _, records = resolve_artifact(args.document, args.kv_root)
    client = redis_client(args)
    dbsize = int(client.dbsize())
    if dbsize <= 0:
        raise RuntimeError("Redis DB is empty; run the inject stage first")

    vllm_metrics_url = f"{args.vllm_url.rstrip('/')}/metrics"
    lmcache_metrics_url = f"{args.lmcache_http_url.rstrip('/')}/metrics"
    vllm_before = parse_prometheus(http_text(vllm_metrics_url), VLLM_METRICS)
    lmcache_before = parse_prometheus(http_text(lmcache_metrics_url), LMCACHE_METRICS)

    payload = {
        "model": args.model,
        "messages": [{"role": "system", "content": normalized}],
        "max_tokens": 1,
        "temperature": 0.0,
        "stream": False,
    }
    started = time.perf_counter()
    response = http_json(
        f"{args.vllm_url.rstrip('/')}/v1/chat/completions",
        payload,
        timeout=args.request_timeout,
    )
    elapsed = time.perf_counter() - started
    time.sleep(args.metrics_wait)

    vllm_after = parse_prometheus(http_text(vllm_metrics_url), VLLM_METRICS)
    lmcache_after = parse_prometheus(http_text(lmcache_metrics_url), LMCACHE_METRICS)
    vllm_delta = metric_delta(vllm_before, vllm_after)
    lmcache_delta = metric_delta(lmcache_before, lmcache_after)

    requested = lmcache_delta["lmcache_mp_lookup_requested_tokens_total"]
    hit = lmcache_delta["lmcache_mp_lookup_hit_tokens_total"]
    hit_rate = hit / requested if requested > 0 else 0.0
    failures = lmcache_delta["lmcache_mp_l2_prefetch_failure_chunks_total"]
    l2_hits = lmcache_delta["lmcache_mp_l2_prefetch_hit_chunks_total"]
    l2_loaded = lmcache_delta["lmcache_mp_l2_prefetch_load_completed_chunks_total"]

    checks = {
        "vllm_external_queries_positive": vllm_delta[
            "vllm:external_prefix_cache_queries_total"
        ]
        > 0,
        "vllm_external_hits_positive": vllm_delta["vllm:external_prefix_cache_hits_total"] > 0,
        "lookup_requested_positive": requested > 0,
        "lookup_full_hit": requested > 0 and hit == requested,
        "l2_prefetch_failure_zero": failures == 0,
        "redis_keys_preserved": int(client.dbsize()) >= len(records),
    }
    if not args.allow_l1_hit:
        checks["l2_hit_positive"] = l2_hits > 0
        checks["l2_load_completed_positive"] = l2_loaded > 0

    result = {
        "ok": all(checks.values()),
        "kid": kid,
        "request_elapsed_seconds": round(elapsed, 3),
        "usage": response.get("usage"),
        "vllm_delta": vllm_delta,
        "lmcache_delta": lmcache_delta,
        "lookup_requested_tokens": int(requested),
        "lookup_hit_tokens": int(hit),
        "lookup_hit_rate": hit_rate,
        "redis_dbsize_after": int(client.dbsize()),
        "checks": checks,
    }
    print_json("CACHE CONSUMPTION", result)
    if not result["ok"]:
        raise RuntimeError(
            "cache-consumption verification failed; restart LMCache/vLLM after injection "
            "to clear L1/GPU state before retrying"
        )
    return result


def build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    normalized, kid = document_identity(args.document)
    base_url = args.kdn_url.rstrip("/")
    register = http_json(
        f"{base_url}/knowledge/register_text",
        {"content": normalized},
        timeout=args.request_timeout,
    )
    returned_kid = str(register.get("kid", "")).strip().lower()
    if returned_kid != kid:
        raise RuntimeError(f"KDN returned kid={returned_kid!r}, expected {kid!r}")

    build_payload = {
        "kid": kid,
        "api_url": f"{args.vllm_url.rstrip('/')}/v1/chat/completions",
        "model": args.model,
        "max_tokens": 1,
        "temperature": 0.0,
        "redis_host": args.redis_host,
        "redis_port": args.redis_port,
        "redis_db": args.redis_db,
        "redis_password": args.redis_password,
        "scan_count": 1000,
        "flushdb": False,
    }
    build = http_json(
        f"{base_url}/knowledge/build_kv",
        build_payload,
        timeout=max(args.request_timeout, 600),
    )
    if int(build.get("dumped_keys", 0)) <= 0:
        raise RuntimeError(f"KDN build produced no keys: {build}")
    result = {"kid": kid, "register": register, "build": build}
    print_json("KDN BUILD", result)
    inspect_artifact(args.document, args.kv_root)
    return result


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--document", type=Path, required=True)
    parser.add_argument(
        "--kv-root",
        type=Path,
        default=REPO_ROOT / "kdn_server" / "KV_database",
    )
    parser.add_argument("--redis-host", default="127.0.0.1")
    parser.add_argument("--redis-port", type=int, default=6379)
    parser.add_argument("--redis-db", type=int, default=0)
    parser.add_argument("--redis-password", default=None)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Register a document and build its KV artifact.")
    add_common(build)
    build.add_argument("--kdn-url", default="http://127.0.0.1:9101")
    build.add_argument("--vllm-url", default="http://127.0.0.1:8000")
    build.add_argument("--model", default="llama3-70b")
    build.add_argument("--request-timeout", type=float, default=300.0)

    inspect = subparsers.add_parser("inspect", help="Validate local manifest/dump metadata.")
    add_common(inspect)

    inject = subparsers.add_parser("inject", help="Restore a local KV artifact into Redis.")
    add_common(inject)
    inject.add_argument("--flush-redis", action="store_true")
    inject.add_argument("--yes", action="store_true", help="Confirm destructive Redis FLUSHDB.")
    inject.add_argument("--allow-extra-keys", action="store_true")
    inject.add_argument("--sample-hashes", type=int, default=3)

    consume = subparsers.add_parser(
        "consume", help="Send the exact builder-style prefix and verify LMCache/vLLM metrics."
    )
    add_common(consume)
    consume.add_argument("--vllm-url", default="http://127.0.0.1:8000")
    consume.add_argument("--lmcache-http-url", default="http://127.0.0.1:8080")
    consume.add_argument("--model", default="llama3-70b")
    consume.add_argument("--request-timeout", type=float, default=300.0)
    consume.add_argument("--metrics-wait", type=float, default=2.0)
    consume.add_argument(
        "--allow-l1-hit",
        action="store_true",
        help="Do not require a new Redis L2 prefetch (useful for repeated runs).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.document = args.document.resolve()
    args.kv_root = args.kv_root.resolve()
    if not args.document.is_file():
        raise FileNotFoundError(f"document not found: {args.document}")

    if args.command == "build":
        build_artifact(args)
    elif args.command == "inspect":
        inspect_artifact(args.document, args.kv_root)
    elif args.command == "inject":
        inject_artifact(args)
    elif args.command == "consume":
        consume_artifact(args)
    else:
        raise AssertionError(args.command)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
