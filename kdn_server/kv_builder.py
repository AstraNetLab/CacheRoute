# kdn_server/kv_builder.py
"""Build KVCache dump directories by triggering vLLM and diffing Redis keys."""
from __future__ import annotations

import base64
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests
import redis

from core.runtime_compat import (
    classify_lmcache_redis_key,
    filter_supported_keys,
    normalize_runtime_profile,
    resolve_scan_match,
)
from .text_db import compute_kid, _normalize_text


def _b64url(s: bytes) -> str:
    # urlsafe base64 without trailing '='
    return base64.urlsafe_b64encode(s).decode("ascii").rstrip("=")


@dataclass
class KVBuildConfig:
    kv_root: str                    # host path: .../kdn_server/KV_database
    api_url: str                    # vLLM OpenAI-compatible endpoint
    model: str
    max_tokens: int = 1
    temperature: float = 0.0

    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None

    # ``auto`` supports both the historical vllm@* layout and newer LMCache
    # model-scoped key layouts. Explicit patterns remain supported.
    match: str = "auto"
    runtime_profile: str = "auto"
    scan_count: int = 1000
    settle_wait_s: float = 0.2      # Redis polling interval.
    settle_rounds: int = 3          # Deprecated compatibility field.
    first_key_timeout_s: float = 30.0
    quiet_period_s: float = 1.5

    flushdb: bool = False           # Warning: clears the entire Redis DB; dangerous.


class KVCacheBuilder:
    """Trigger inference, capture LMCache Redis blocks, and persist them."""

    def __init__(self, cfg: KVBuildConfig, text_db=None):
        self.cfg = cfg
        self.runtime_profile = normalize_runtime_profile(cfg.runtime_profile)
        self.scan_match = resolve_scan_match(self.runtime_profile, cfg.match)
        self.rds = redis.Redis(
            host=cfg.redis_host,
            port=cfg.redis_port,
            db=cfg.redis_db,
            password=cfg.redis_password,
            decode_responses=False,
        )
        self.text_db = text_db

    def build_from_text_file(self, txt_path: str) -> Dict:
        p = Path(txt_path).resolve()
        content = p.read_text(encoding="utf-8")
        return self.build_from_text(content)

    def build_from_text(self, text: str) -> Dict:
        norm = _normalize_text(text)
        if not norm:
            raise ValueError("text is empty after normalization")

        kid = compute_kid(norm)
        out_dir = Path(self.cfg.kv_root).resolve() / kid

        if out_dir.exists():
            shutil.rmtree(out_dir)
        (out_dir / "blocks").mkdir(parents=True, exist_ok=True)

        wait_started = time.monotonic()
        try:
            if self.cfg.flushdb:
                self.rds.flushdb()

            keys_before = self._scan_keys_set()
            self._trigger_infer(norm)
            keys_after = self._wait_keys_settle_set(keys_before)
            keys_new = sorted(keys_after - keys_before)

            manifest_path = out_dir / "manifest.jsonl"
            dumped = self._dump_keys(keys_new, out_dir / "blocks", manifest_path)
            if dumped <= 0:
                raise RuntimeError(
                    "KV build failed: no LMCache Redis keys were dumped; "
                    f"profile={self.runtime_profile!r}, requested_match={self.cfg.match!r}, "
                    f"scan_match={self.scan_match!r}, keys_before={len(keys_before)}, "
                    f"keys_after={len(keys_after)}, keys_new={len(keys_new)}"
                )

            key_formats = sorted({
                classify_lmcache_redis_key(key) or "explicit"
                for key in keys_new
            })
            meta = {
                "kid": kid,
                "time": int(time.time()),
                "api_url": self.cfg.api_url,
                "model": self.cfg.model,
                "max_tokens": self.cfg.max_tokens,
                "temperature": self.cfg.temperature,
                "runtime_profile": self.runtime_profile,
                "key_formats": key_formats,
                "redis": {
                    "host": self.cfg.redis_host,
                    "port": self.cfg.redis_port,
                    "db": self.cfg.redis_db,
                    "requested_match": self.cfg.match,
                    "scan_match": self.scan_match,
                },
                "capture": {
                    "poll_interval_s": self.cfg.settle_wait_s,
                    "first_key_timeout_s": self.cfg.first_key_timeout_s,
                    "quiet_period_s": self.cfg.quiet_period_s,
                    "elapsed_s": round(time.monotonic() - wait_started, 3),
                },
                "dumped_keys": dumped,
                "keys_before": len(keys_before),
                "keys_after": len(keys_after),
                "keys_new": len(keys_new),
            }
            (out_dir / "run_meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            if self.text_db is not None:
                self.text_db.mark_kv_ready(
                    kid=kid,
                    kv_rel_dir=kid,
                    dumped_keys=dumped,
                    updated_at=meta["time"],
                )

            return {
                "kid": kid,
                "kv_dir": str(out_dir),
                "dumped_keys": dumped,
                "runtime_profile": self.runtime_profile,
                "key_formats": key_formats,
            }
        except Exception:
            # Never leave an empty/partial KV directory that could later be
            # mistaken for a ready knowledge block.
            shutil.rmtree(out_dir, ignore_errors=True)
            raise

    def _trigger_infer(self, prompt: str) -> None:
        payload = {
            "model": self.cfg.model,
            "messages": [{"role": "system", "content": prompt}],
            "max_tokens": self.cfg.max_tokens,
            "temperature": self.cfg.temperature,
            "stream": False,
        }
        response = requests.post(self.cfg.api_url, json=payload, timeout=300)
        response.raise_for_status()

    def _scan_keys_set(self) -> set[bytes]:
        raw_keys = set(self._scan_keys())
        return filter_supported_keys(
            raw_keys,
            profile=self.runtime_profile,
            requested_match=self.cfg.match,
        )

    def _wait_keys_settle_set(self, keys_before: set[bytes]) -> set[bytes]:
        """Wait for asynchronous LMCache remote writes without fixed delay.

        Empty scans never count as stable. Once new keys appear, the function
        returns after the set remains unchanged for ``quiet_period_s``. The
        timeout is an upper bound, not a per-registration sleep.
        """
        timeout_s = max(0.1, float(self.cfg.first_key_timeout_s))
        quiet_period_s = max(0.0, float(self.cfg.quiet_period_s))
        poll_s = max(0.01, float(self.cfg.settle_wait_s))
        deadline = time.monotonic() + timeout_s

        latest_keys = set(keys_before)
        last_new_keys: Optional[set[bytes]] = None
        last_change_ts: Optional[float] = None

        while time.monotonic() < deadline:
            time.sleep(poll_s)
            latest_keys = self._scan_keys_set()
            new_keys = latest_keys - keys_before
            now = time.monotonic()

            if not new_keys:
                continue

            if last_new_keys is None or new_keys != last_new_keys:
                last_new_keys = set(new_keys)
                last_change_ts = now
                continue

            if last_change_ts is not None and now - last_change_ts >= quiet_period_s:
                return latest_keys

        dbsize = None
        try:
            dbsize = int(self.rds.dbsize())
        except Exception:
            pass

        if not last_new_keys:
            raise TimeoutError(
                "LMCache produced no matching Redis keys before timeout; "
                f"timeout_s={timeout_s}, profile={self.runtime_profile!r}, "
                f"requested_match={self.cfg.match!r}, scan_match={self.scan_match!r}, "
                f"redis={self.cfg.redis_host}:{self.cfg.redis_port}/{self.cfg.redis_db}, "
                f"dbsize={dbsize}"
            )

        raise TimeoutError(
            "LMCache Redis keys appeared but did not become quiet before timeout; "
            f"timeout_s={timeout_s}, captured_new_keys={len(last_new_keys)}"
        )

    def _scan_keys(self) -> List[bytes]:
        cursor = 0
        out: List[bytes] = []
        while True:
            cursor, batch = self.rds.scan(
                cursor=cursor,
                match=self.scan_match,
                count=self.cfg.scan_count,
            )
            out.extend(batch)
            if cursor == 0:
                break
        return out

    def _wait_keys_settle(self) -> List[bytes]:
        """Deprecated compatibility wrapper for older direct callers."""
        before = self._scan_keys_set()
        return list(self._wait_keys_settle_set(before))

    def _dump_keys(self, keys: Iterable[bytes], blocks_dir: Path, manifest_path: Path) -> int:
        dumped = 0
        with manifest_path.open("w", encoding="utf-8") as mf:
            for key in keys:
                value = self.rds.get(key)
                if value is None:
                    continue

                fname = _b64url(key) + ".dump"
                fpath = blocks_dir / fname
                fpath.write_bytes(value)

                rec = {
                    "key_b64url": _b64url(key),
                    "file": f"blocks/{fname}",
                    "bytes": len(value),
                }
                mf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                dumped += 1
        return dumped
