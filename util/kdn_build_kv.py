#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

# Support direct execution from a source checkout before project imports.
REPO_ROOT = Path(__file__).resolve().parents[1]
for source_root in (REPO_ROOT, REPO_ROOT / "src"):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

from kdn_server.kv_builder import KVBuildConfig, KVCacheBuilder


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--txt", required=True, help="Path to txt knowledge block")
    ap.add_argument("--kv-root", required=True, help="KV_database root path")

    ap.add_argument("--api-url", default="http://127.0.0.1:8000/v1/chat/completions")
    ap.add_argument("--model", required=True)
    ap.add_argument("--max-tokens", type=int, default=1)
    ap.add_argument("--temperature", type=float, default=0.0)

    ap.add_argument("--redis-host", default="127.0.0.1")
    ap.add_argument("--redis-port", type=int, default=6379)
    ap.add_argument("--redis-db", type=int, default=0)
    ap.add_argument("--match", default="vllm@*")
    ap.add_argument("--scan-count", type=int, default=1000)
    ap.add_argument("--flushdb", action="store_true")

    args = ap.parse_args()

    txt = Path(args.txt).resolve()
    if not txt.exists():
        raise FileNotFoundError(txt)

    cfg = KVBuildConfig(
        kv_root=str(Path(args.kv_root).resolve()),
        api_url=args.api_url,
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        redis_db=args.redis_db,
        match=args.match,
        scan_count=args.scan_count,
        flushdb=args.flushdb,
    )
    builder = KVCacheBuilder(cfg)
    out = builder.build_from_text_file(str(txt))
    print(out)


if __name__ == "__main__":
    main()
