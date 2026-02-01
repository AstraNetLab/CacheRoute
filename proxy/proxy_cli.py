#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CacheRoute Proxy CLI (REPL)

Focus:
- Inspect proxy control plane (8002): instance pool status/list
- Optionally inspect scheduler control plane (7002): whether this proxy is registered

This CLI does NOT import proxy internals; it talks via HTTP only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shlex
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx


def _fmt_ts(ts: Any) -> str:
    """Format unix timestamp (seconds) to readable local time."""
    try:
        ts_i = int(ts)
        return _dt.datetime.fromtimestamp(ts_i).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def _short(s: Any, max_len: int = 80) -> str:
    try:
        s = json.dumps(s, ensure_ascii=False) if isinstance(s, (dict, list)) else str(s)
    except Exception:
        s = str(s)
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _print_kv(title: str, kv: List[Tuple[str, Any]]) -> None:
    print(title)
    for k, v in kv:
        print(f"  - {k}: {v}")


def _print_table(rows: List[List[str]], headers: List[str]) -> None:
    if not rows:
        print("(empty)")
        return
    cols = len(headers)
    widths = [len(h) for h in headers]
    for r in rows:
        for i in range(cols):
            widths[i] = max(widths[i], len(r[i]))

    def _line(parts: List[str]) -> str:
        return " | ".join(parts[i].ljust(widths[i]) for i in range(cols))

    print(_line(headers))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(_line(r))


class ProxyCLI:
    def __init__(
        self,
        cp_url: str,
        scheduler_cp_url: str,
        proxy_id: str,
        scheduler_proxy_list_path: str,
        timeout_s: float = 5.0,
    ) -> None:
        self.cp_url = cp_url.rstrip("/")
        self.scheduler_cp_url = scheduler_cp_url.rstrip("/")
        self.proxy_id = proxy_id.strip()
        self.scheduler_proxy_list_path = scheduler_proxy_list_path
        self.client = httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        self.client.close()

    # ---------------- Proxy CP helpers ----------------

    def cp_get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any] | List[Any]:
        url = f"{self.cp_url}{path}"
        r = self.client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def cmd_status(self) -> None:
        """
        Show proxy control plane health + instance counts.
        Prefer /debug/status if present; fallback to /healthz + /v1/instance/list.
        """
        # healthz (always)
        try:
            health = self.cp_get_json("/healthz")
        except Exception as e:
            print(f"[ERR] proxy cp healthz failed: cp_url={self.cp_url} err={e}")
            return

        # debug/status (optional)
        debug = None
        try:
            debug = self.cp_get_json("/debug/status")
        except Exception:
            debug = None

        if isinstance(health, dict):
            ttl_s = health.get("ttl_s", None)
        else:
            ttl_s = None

        alive_cnt = None
        total_cnt = None
        sample_ids: List[str] = []

        if isinstance(debug, dict):
            alive_cnt = debug.get("alive_instances", None)
            total_cnt = debug.get("total_instances", None)
            sample_ids = debug.get("sample_ids", []) or []
        else:
            # fallback: list instances and count
            try:
                alive_items = self.cp_get_json("/v1/instance/list", params={"include_dead": "false"})
                dead_items = self.cp_get_json("/v1/instance/list", params={"include_dead": "true"})
                alive_cnt = len(alive_items) if isinstance(alive_items, list) else None
                total_cnt = len(dead_items) if isinstance(dead_items, list) else None
                if isinstance(alive_items, list):
                    sample_ids = [str(x.get("instance_id")) for x in alive_items[:10]]
            except Exception:
                pass

        _print_kv(
            "[ProxyCP] status",
            [
                ("cp_url", self.cp_url),
                ("ttl_s", ttl_s),
                ("alive_instances", alive_cnt),
                ("total_instances", total_cnt),
                ("sample_ids", sample_ids),
            ],
        )

    def cmd_instances(self, include_dead: bool, limit: int) -> None:
        try:
            items = self.cp_get_json("/v1/instance/list", params={"include_dead": "true" if include_dead else "false"})
        except Exception as e:
            print(f"[ERR] proxy cp list failed: cp_url={self.cp_url} err={e}")
            return

        if not isinstance(items, list):
            print(f"[ERR] unexpected list payload: {type(items)} {items}")
            return

        rows: List[List[str]] = []
        now = int(time.time())
        for it in items[: max(0, limit)]:
            iid = str(it.get("instance_id", ""))
            host = str(it.get("host", ""))
            port = str(it.get("port", ""))
            last_seen = it.get("last_seen_at", None)
            registered = it.get("registered_at", None)
            meta = it.get("meta", {}) or {}
            # if control plane didn't compute is_alive, derive a best-effort one
            is_alive = it.get("is_alive", None)
            if is_alive is None and last_seen is not None:
                # ttl unknown here; show age
                pass

            age_s = ""
            try:
                if last_seen is not None:
                    age_s = str(max(0, now - int(last_seen)))
            except Exception:
                age_s = ""

            rows.append(
                [
                    iid,
                    f"{host}:{port}",
                    _fmt_ts(registered),
                    _fmt_ts(last_seen),
                    age_s,
                    _short(meta, 48),
                ]
            )

        headers = ["instance_id", "addr", "registered_at", "last_seen_at", "age_s", "meta"]
        _print_table(rows, headers)
        print(f"\ncount={len(items)} shown={min(len(items), limit)} include_dead={include_dead}")

    def cmd_watch(self, include_dead: bool, interval_s: float, limit: int) -> None:
        print("[watch] press Ctrl+C to stop")
        try:
            while True:
                # crude clear screen
                print("\033[2J\033[H", end="")
                self.cmd_status()
                print()
                self.cmd_instances(include_dead=include_dead, limit=limit)
                time.sleep(max(0.2, interval_s))
        except KeyboardInterrupt:
            print("\n[watch] stopped")

    # ---------------- Scheduler CP helpers ----------------

    def scheduler_get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any] | List[Any]:
        url = f"{self.scheduler_cp_url}{path}"
        r = self.client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def cmd_scheduler(self, include_dead: bool = True) -> None:
        """
        Show this proxy's registration on scheduler control plane.
        Endpoint path can vary between versions; default is /v1/proxy/list.

        If it fails with 404, pass --scheduler-proxy-list-path to match your scheduler.
        """
        if not self.proxy_id:
            env_host = os.environ.get("PROXY_ADVERTISE_HOST", "").strip()
            env_port = os.environ.get("PROXY_ADVERTISE_PORT", "").strip()
            try:
                items = self.scheduler_get_json(
                    self.scheduler_proxy_list_path,
                    params={"include_dead": "true"},
                )
            except Exception as e:
                print("[ERR] proxy_id is empty and scheduler list fetch failed: err=%s" % e)
                print("      Provide --proxy-id or set env PROXY_ID.")
                return

            if not isinstance(items, list) or not items:
                print("[ERR] scheduler proxy list is empty; cannot infer proxy_id.")
                print("      Provide --proxy-id or set env PROXY_ID.")
                return

            # Try match by advertise host/port from env
            if env_host and env_port:
                for it in items:
                    if str(it.get("host", "")) == env_host and str(it.get("port", "")) == str(env_port):
                        self.proxy_id = str(it.get("proxy_id", "")).strip()
                        break

            # If still empty, and only one proxy exists, auto-pick it
            if not self.proxy_id and len(items) == 1:
                self.proxy_id = str(items[0].get("proxy_id", "")).strip()

            if not self.proxy_id:
                inferred = self._infer_proxy_id_from_scheduler()
                if inferred:
                    self.proxy_id = inferred
                else:
                    print("[ERR] proxy_id is empty and cannot be inferred.")
                    print("      Provide --proxy-id <id> or set env PROXY_ID.")
                    print("      (Tip) If multiple proxies exist, export PROXY_ADVERTISE_HOST/PORT for auto-match.")
                    return

        try:
            items = self.scheduler_get_json(
                self.scheduler_proxy_list_path,
                params={"include_dead": "true" if include_dead else "false"},
            )
        except Exception as e:
            print(
                "[ERR] scheduler query failed: scheduler_cp_url=%s path=%s err=%s"
                % (self.scheduler_cp_url, self.scheduler_proxy_list_path, e)
            )
            print("      Hint: if endpoint differs, set --scheduler-proxy-list-path.")
            return

        if not isinstance(items, list):
            print(f"[ERR] unexpected scheduler list payload: {type(items)} {items}")
            return

        hit = None
        for it in items:
            pid = str(it.get("proxy_id", ""))
            if pid == self.proxy_id:
                hit = it
                break

        if not hit:
            print(f"[SchedulerCP] proxy NOT FOUND: proxy_id={self.proxy_id}")
            return

        _print_kv(
            "[SchedulerCP] proxy",
            [
                ("scheduler_cp_url", self.scheduler_cp_url),
                ("proxy_id", self.proxy_id),
                ("addr", f"{hit.get('host')}:{hit.get('port')}"),
                ("registered_at", _fmt_ts(hit.get("registered_at"))),
                ("last_seen_at", _fmt_ts(hit.get("last_seen_at"))),
                ("load", hit.get("load")),
                ("meta", hit.get("meta")),
            ],
        )

    def _infer_proxy_id_from_scheduler(self) -> str:
        """Best-effort infer proxy_id from scheduler proxy list."""
        env_host = os.environ.get("PROXY_ADVERTISE_HOST", "").strip()
        env_port = os.environ.get("PROXY_ADVERTISE_PORT", "").strip()

        try:
            items = self.scheduler_get_json(
                self.scheduler_proxy_list_path,
                params={"include_dead": "true"},
            )
        except Exception:
            return ""

        if not isinstance(items, list) or not items:
            return ""

        # 1) Match by advertise host/port if provided
        if env_host and env_port:
            for it in items:
                if str(it.get("host", "")) == env_host and str(it.get("port", "")) == str(env_port):
                    return str(it.get("proxy_id", "")).strip()

        # 2) Auto-pick if only one proxy exists
        if len(items) == 1:
            return str(items[0].get("proxy_id", "")).strip()

        return ""

    # ---------------- REPL ----------------

    def help(self) -> None:
        print(
            """
Commands:
  :help
  :status
      Show proxy control plane health + instance counts.
  :instances [N]
      List alive instances (default N=20).
  :instances --all [N]
      List all instances including dead (include_dead=true).
  :watch [--all] [--interval S] [--limit N]
      Refresh status + instances periodically (Ctrl+C to stop).
  :scheduler
      Query scheduler control plane and show this proxy's registration.
  :quit / :exit

Examples:
  :status
  :instances
  :instances --all 50
  :watch --interval 1 --limit 30
  :scheduler
"""
        )

    def repl(self) -> None:
        if not self.proxy_id:
            inferred = self._infer_proxy_id_from_scheduler()
            if inferred:
                self.proxy_id = inferred

        print("CacheRoute Proxy CLI (REPL)")
        print(f"  proxy_cp={self.cp_url}")
        print(f"  scheduler_cp={self.scheduler_cp_url}")
        print(f"  proxy_id={self.proxy_id or '(empty)'}")
        print("Type :help for commands.\n")
        self.help()

        while True:
            try:
                line = input("proxy> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nbye.")
                break

            if not line:
                continue

            if not line.startswith(":"):
                print("Commands must start with ':'. Try :help")
                continue

            try:
                argv = shlex.split(line[1:])
            except ValueError as e:
                print(f"[ERR] parse error: {e}")
                continue

            cmd = argv[0] if argv else ""
            args = argv[1:]

            if cmd in ("quit", "exit"):
                print("bye.")
                break
            if cmd == "help":
                self.help()
                continue
            if cmd == "status":
                self.cmd_status()
                continue
            if cmd == "instances":
                include_dead = False
                limit = 20
                # parse flags
                rest: List[str] = []
                for a in args:
                    if a == "--all":
                        include_dead = True
                    else:
                        rest.append(a)
                if rest:
                    try:
                        limit = int(rest[0])
                    except Exception:
                        print("[ERR] instances: N must be int")
                        continue
                self.cmd_instances(include_dead=include_dead, limit=limit)
                continue
            if cmd == "watch":
                include_dead = False
                interval_s = 1.0
                limit = 20
                it = iter(args)
                ok = True
                for a in it:
                    if a == "--all":
                        include_dead = True
                    elif a == "--interval":
                        try:
                            interval_s = float(next(it))
                        except Exception:
                            ok = False
                            break
                    elif a == "--limit":
                        try:
                            limit = int(next(it))
                        except Exception:
                            ok = False
                            break
                    else:
                        print(f"[ERR] unknown flag: {a}")
                        ok = False
                        break
                if not ok:
                    print("Usage: :watch [--all] [--interval S] [--limit N]")
                    continue
                self.cmd_watch(include_dead=include_dead, interval_s=interval_s, limit=limit)
                continue
            if cmd == "scheduler":
                self.cmd_scheduler(include_dead=True)
                continue

            print(f"[ERR] unknown command: {cmd}. Try :help")


def main() -> int:
    parser = argparse.ArgumentParser(description="CacheRoute Proxy CLI (REPL)")
    parser.add_argument("--cp-url", default=os.environ.get("PROXY_CP_URL", "http://127.0.0.1:8002"))
    parser.add_argument("--scheduler-cp-url", default=os.environ.get("SCHEDULER_CP_URL", "http://127.0.0.1:7002"))
    parser.add_argument("--proxy-id", default=os.environ.get("PROXY_ID", ""))
    parser.add_argument(
        "--scheduler-proxy-list-path",
        default=os.environ.get("SCHEDULER_PROXY_LIST_PATH", "/v1/proxy/list"),
        help="Scheduler CP path that returns list of proxies (JSON list).",
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    cli = ProxyCLI(
        cp_url=args.cp_url,
        scheduler_cp_url=args.scheduler_cp_url,
        proxy_id=args.proxy_id,
        scheduler_proxy_list_path=args.scheduler_proxy_list_path,
        timeout_s=args.timeout,
    )
    try:
        cli.repl()
    finally:
        cli.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
