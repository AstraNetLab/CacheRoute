import argparse
import os
import shlex
import time
import requests

"""
Scheduler CLI (HTTP Client)

Why this CLI:
- Run Scheduler in one terminal
- Run this CLI in another terminal
- The CLI fetches realtime state via Scheduler debug endpoints

Required Scheduler endpoints:
- GET  /debug/status
- POST /debug/knowledge/peek

Usage:
  python3 scheduler_cli.py --base-url http://127.0.0.1:7001

Interactive commands:
  :help                          show help
  :status                        show scheduler knowledge summary (entries/dim/faiss/kdn source)
  :fields                        show KnowledgeUnit fields discovered from scheduler
  :list [N]                      list first N kids (default 10)
  :peek <kid> [kid2 ...]         show basic metadata for specified kids
  :exit / :quit                  exit CLI
"""

DEFAULT_BASE_URL = os.getenv("SCHEDULER_BASE_URL", "http://127.0.0.1:7001").rstrip("/")
DEFAULT_TIMEOUT = 10


def http_get(base_url: str, path: str, timeout_s: int = DEFAULT_TIMEOUT) -> dict:
    r = requests.get(f"{base_url}{path}", timeout=timeout_s)
    r.raise_for_status()
    return r.json()


def http_post(base_url: str, path: str, payload: dict, timeout_s: int = DEFAULT_TIMEOUT) -> dict:
    r = requests.post(f"{base_url}{path}", json=payload, timeout=timeout_s)
    r.raise_for_status()
    return r.json()


def _fmt_ts(ts: int | None) -> str:
    if not ts:
        return "None"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ts)))


def cmd_status(base_url: str):
    s = http_get(base_url, "/debug/status")
    print("[STATUS]")
    print(f"  knowledge_loaded: {s.get('knowledge_loaded')}")
    print(f"  entries: {s.get('entries')}")
    print(f"  dim: {s.get('dim')}")
    print(f"  faiss_total: {s.get('faiss_total')}")
    print(f"  kdn_base_url: {s.get('kdn_base_url')}")
    print(f"  last_refresh_ts: {s.get('last_refresh_ts')} ({_fmt_ts(s.get('last_refresh_ts'))})")

    sample = s.get("sample_kids") or []
    if sample:
        print("  sample_kids[0:10]:")
        for k in sample:
            print(f"    - {k}")


def cmd_fields(base_url: str):
    s = http_get(base_url, "/debug/status")
    fields = s.get("unit_fields") or []
    print("[UNIT_FIELDS]")
    if not fields:
        print("  (empty)  -> maybe knowledge not loaded or no sample unit")
        return
    for f in fields:
        print(f"  - {f}")


def cmd_list(base_url: str, n: int = 10):
    s = http_get(base_url, "/debug/status")
    kids = s.get("sample_kids") or []
    kids = kids[: max(1, n)]
    print(f"[LIST] first {len(kids)} kids:")
    for k in kids:
        print(f"  - {k}")


def cmd_peek(base_url: str, kids: list[str]):
    kids = [k.strip().lower() for k in kids if k.strip()]
    if not kids:
        print("[ERROR] usage: :peek <kid> [kid2 ...]")
        return

    payload = {
        "kids": kids,
        # 默认只看安全字段，避免输出大 embedding
        "need_fields": ["length", "avail_kdn_servers", "avail_llm_systems", "kv_ready","kv_dumped_keys"],
    }
    r = http_post(base_url, "/debug/knowledge/peek", payload)
    items = r.get("items") or []
    miss = r.get("miss") or []

    print("[PEEK]")
    for it in items:
        kid = it.get("kid")
        length = it.get("length")
        servers = it.get("avail_kdn_servers")
        llm_servers = it.get("avail_llm_systems")
        kv_ready = it.get("kv_ready")
        kv_dumped_keys = it.get("kv_dumped_keys")
        print(f"  kid: {kid}")
        print(f"    length: {length}")
        print(f"    avail_kdn_servers: {servers}")
        print(f"    avail_llm_systems: {llm_servers}")
        print(f"    kv_ready: {kv_ready}")
        print(f"    kv_dumped_keys: {kv_dumped_keys}")

    if miss:
        print("[MISS]")
        for k in miss:
            print(f"  - {k}")


def cmd_refresh(base_url: str):
    r = http_post(base_url, "/admin/refresh_knowledge", payload={})
    print("[REFRESH]")
    print(r)


def print_help():
    print("=" * 80)
    print("Scheduler CLI (HTTP)")
    print("")
    print("Commands:")
    print("  :status                show scheduler knowledge summary")
    print("  :fields                show KnowledgeUnit fields stored in scheduler")
    print("  :list [N]              list first N kids (default 10)")
    print("  :peek <kid> [kid2 ...] show basic metadata for specified kids")
    print("  :refresh               trigger refresh from KDN immediately")
    print("  :exit / :quit          exit CLI")
    print("=" * 80)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Scheduler base url, e.g. http://127.0.0.1:7001")
    args = ap.parse_args()
    base_url = args.base_url.rstrip("/")

    print_help()
    print(f"[CLI] scheduler={base_url}")

    while True:
        try:
            line = input("[sch] ").strip()
        except EOFError:
            break
        except KeyboardInterrupt:
            print("\n^C")
            break

        if not line:
            continue

        if line in (":exit", ":quit"):
            break

        if line in (":help", "help"):
            print_help()
            continue

        # status
        if line == ":status":
            try:
                cmd_status(base_url)
            except Exception as e:
                print(f"[ERROR] status failed: {e}")
            continue

        # fields
        if line == ":fields":
            try:
                cmd_fields(base_url)
            except Exception as e:
                print(f"[ERROR] fields failed: {e}")
            continue

        # list
        if line.startswith(":list"):
            tokens = shlex.split(line)
            n = 10
            if len(tokens) >= 2:
                try:
                    n = int(tokens[1])
                except Exception:
                    n = 10
            try:
                cmd_list(base_url, n=n)
            except Exception as e:
                print(f"[ERROR] list failed: {e}")
            continue

        # peek
        if line.startswith(":peek "):
            tokens = shlex.split(line)
            kids = tokens[1:]
            try:
                cmd_peek(base_url, kids)
            except Exception as e:
                print(f"[ERROR] peek failed: {e}")
            continue

        # refresh
        if line == ":refresh":
            try:
                cmd_refresh(base_url)
            except Exception as e:
                print(f"[ERROR] refresh failed: {e}")
            continue

        print(f"[ERROR] Unknown command: {line!r}")
        print("        use ':help' to see available commands")

    print("bye.")


if __name__ == "__main__":
    main()
