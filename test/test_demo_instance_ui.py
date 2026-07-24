import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path
import types
from collections import deque

import importlib.util
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

fake_config = types.SimpleNamespace(
    INSTANCE_RESOURCE_MONITOR_ENABLE=True,
    INSTANCE_RESOURCE_AUTO_START_AGENT=True,
    INSTANCE_RESOURCE_AGENT_LISTEN="127.0.0.1:9201",
    INSTANCE_RESOURCE_AGENT_URL="http://127.0.0.1:9201",
    INSTANCE_RESOURCE_AGENT_SAMPLE_INTERVAL_MS=1000,
    INSTANCE_RESOURCE_AGENT_START_TIMEOUT_S=60.0,
    INSTANCE_RESOURCE_REPORT_ENABLE=False,
    INSTANCE_RESOURCE_REPORT_HZ=1.0,
    INSTANCE_RESOURCE_REPORT_TIMEOUT_S=2.0,
    INSTANCE_UI_ENABLE=False,
    INSTANCE_UI_LISTEN="0.0.0.0:9202",
    INSTANCE_UI_OPEN_BROWSER=False,
    INSTANCE_UI_START_TIMEOUT_S=5.0,
    INSTANCE_PORT=9001,
    INSTANCE_HOST="127.0.0.1",
    PROXY_CP_URL="http://127.0.0.1:8002",
)
fake_core = types.ModuleType("core")
fake_core.config = fake_config
sys.modules.setdefault("core", fake_core)
sys.modules.setdefault("core.config", fake_config)
fake_uvicorn = types.ModuleType("uvicorn")
fake_uvicorn.run = lambda *args, **kwargs: None
sys.modules.setdefault("uvicorn", fake_uvicorn)
fake_reporter = types.ModuleType("instance.resource_agent.proxy_reporter")
fake_reporter.report_once = lambda *args, **kwargs: True
sys.modules.setdefault("instance.resource_agent.proxy_reporter", fake_reporter)
config = fake_config

spec = importlib.util.spec_from_file_location("demo_instance", os.path.join(os.path.dirname(__file__), "demo_instance.py"))
demo_instance = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(demo_instance)


def test_ui_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INSTANCE_UI_ENABLE", raising=False)
    args = demo_instance.parse_args([])
    assert args.ui_enabled is False


def test_ui_flags_and_env_precedence(monkeypatch):
    monkeypatch.setenv("INSTANCE_UI_ENABLE", "1")
    assert demo_instance.parse_args(["--no-ui"]).ui_enabled is False
    assert demo_instance.parse_args(["--ui"]).ui_enabled is True
    monkeypatch.setenv("INSTANCE_UI_LISTEN", "127.0.0.1:12345")
    monkeypatch.setenv("INSTANCE_UI_START_TIMEOUT_S", "9")
    args = demo_instance.parse_args(["--ui-listen", "127.0.0.1:23456", "--ui-start-timeout-s", "1.5"])
    assert args.ui_listen == "127.0.0.1:23456"
    assert args.ui_start_timeout_s == 1.5


def test_browser_open_resolution(monkeypatch):
    monkeypatch.delenv("INSTANCE_UI_OPEN_BROWSER", raising=False)
    assert demo_instance.parse_args(["--ui"]).ui_open_browser_resolved is True
    assert demo_instance.parse_args(["--ui", "--no-ui-open-browser"]).ui_open_browser_resolved is False
    assert demo_instance.parse_args(["--ui-open-browser"]).ui_open_browser_resolved is True
    monkeypatch.setenv("INSTANCE_UI_ENABLE", "1")
    monkeypatch.setenv("INSTANCE_UI_OPEN_BROWSER", "0")
    assert demo_instance.parse_args([]).ui_open_browser_resolved is False


def test_invalid_ui_listen_fails():
    with pytest.raises(SystemExit):
        demo_instance.parse_args(["--ui-listen", "bad"])


def test_dashboard_command_uses_runtime_values():
    d = demo_instance.DemoDashboard(
        enabled=True,
        listen="0.0.0.0:9202",
        open_browser=False,
        start_timeout_s=5,
        agent_listen="127.0.0.1:19201",
        sample_interval_ms=250,
    )
    cmd = d.build_command("runtime-id")
    assert cmd[0] == sys.executable
    assert cmd[1].endswith("instance/resource_dashboard/dashboard_server.py")
    assert "--no-auto-start" in cmd
    assert cmd[cmd.index("--agent-listen") + 1] == "127.0.0.1:19201"
    assert cmd[cmd.index("--sample-interval-ms") + 1] == "250"
    assert cmd[cmd.index("--instance-id") + 1] == "runtime-id"
    assert cmd[cmd.index("--dashboard-listen") + 1] == "0.0.0.0:9202"


def test_dashboard_url_maps_wildcard_hosts():
    assert demo_instance.dashboard_url_for_listen("0.0.0.0:9202") == "http://127.0.0.1:9202"
    assert demo_instance.dashboard_url_for_listen("[::]:9202") == "http://127.0.0.1:9202"
    assert demo_instance.dashboard_url_for_listen("::1:9202") == "http://[::1]:9202"


class FakeProc:
    def __init__(self, poll_values=None):
        self.pid = 4321
        self.stdout = None
        self.stderr = None
        self.wait_calls = []
        self._poll_values = list(poll_values or [None])

    def poll(self):
        return self._poll_values[0] if self._poll_values else None

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        if timeout == 3 and len(self.wait_calls) == 1:
            raise subprocess.TimeoutExpired("cmd", timeout)
        self._poll_values = [0]
        return 0


class Logger:
    def __init__(self):
        self.messages = []
    def info(self, *args): self.messages.append(("info", args))
    def warning(self, *args): self.messages.append(("warning", args))
    def debug(self, *args): self.messages.append(("debug", args))


def test_reuse_existing_dashboard_does_not_spawn_or_stop(monkeypatch):
    calls = []
    d = demo_instance.DemoDashboard(enabled=True, listen="127.0.0.1:9202", open_browser=False, start_timeout_s=0.1, agent_listen="127.0.0.1:9201", sample_interval_ms=1000)
    monkeypatch.setattr(d, "_health_ok", lambda timeout_s=0.5: True)
    monkeypatch.setattr(demo_instance.subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
    asyncio.run(d.start(runtime_instance_id="id", logger=Logger()))
    asyncio.run(d.stop(logger=Logger()))
    assert calls == []


def test_start_timeout_nonfatal_and_bounded_tails(monkeypatch):
    d = demo_instance.DemoDashboard(enabled=True, listen="127.0.0.1:9202", open_browser=False, start_timeout_s=0.01, agent_listen="127.0.0.1:9201", sample_interval_ms=1000)
    fake = FakeProc()
    d._stdout_tail = deque([f"out{i}\n" for i in range(30)], maxlen=20)
    d._stderr_tail = deque([f"err{i}\n" for i in range(30)], maxlen=20)
    monkeypatch.setattr(d, "_health_ok", lambda timeout_s=0.5: False)
    monkeypatch.setattr(demo_instance.subprocess, "Popen", lambda *a, **k: fake)
    log = Logger()
    asyncio.run(d.start(runtime_instance_id="id", logger=log))
    assert d._started_dashboard is True
    assert "out0" not in demo_instance.DemoResourceMonitor._read_tail(d._stdout_tail)
    assert any(m[0] == "warning" for m in log.messages)


def test_browser_open_success_failure_and_disabled(monkeypatch):
    opened = []
    d = demo_instance.DemoDashboard(enabled=True, listen="127.0.0.1:9202", open_browser=True, start_timeout_s=0.1, agent_listen="127.0.0.1:9201", sample_interval_ms=1000)
    monkeypatch.setattr(d, "_health_ok", lambda timeout_s=0.5: len(opened) == 0)
    monkeypatch.setattr(demo_instance.webbrowser, "open", lambda url: opened.append(url) or False)
    log = Logger()
    asyncio.run(d.start(runtime_instance_id="id", logger=log))
    assert opened == ["http://127.0.0.1:9202"]
    assert any(m[0] == "warning" for m in log.messages)


def test_cleanup_terminates_process_group_and_escalates(monkeypatch):
    d = demo_instance.DemoDashboard(enabled=True, listen="127.0.0.1:9202", open_browser=False, start_timeout_s=0.1, agent_listen="127.0.0.1:9201", sample_interval_ms=1000)
    d._proc = FakeProc()
    d._started_dashboard = True
    signals = []
    monkeypatch.setattr(demo_instance.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    asyncio.run(d.stop(logger=Logger()))
    assert signals == [(4321, signal.SIGTERM), (4321, signal.SIGKILL)]
    asyncio.run(d.stop(logger=Logger()))


def test_ui_disabled_creates_no_dashboard_process():
    d = demo_instance.DemoDashboard(enabled=False, listen=config.INSTANCE_UI_LISTEN, open_browser=False, start_timeout_s=1, agent_listen="127.0.0.1:9201", sample_interval_ms=1000)
    assert d.enabled is False
    assert d._proc is None


def test_instance_lifecycle_starts_dashboard_outside_registration_success_branch():
    source = (ROOT_DIR / "instance" / "instance_api.py").read_text()
    assert "await dashboard.start(runtime_instance_id=runtime_instance_id, logger=logger)" in source
    assert "if dashboard is not None:\n        await dashboard.start" in source
    assert "await dashboard.stop(logger=logger)" in source


def test_resource_agent_for_ui_uses_monitor_owner_without_reporting():
    source = (ROOT_DIR / "test" / "demo_instance.py").read_text()
    assert "async def ensure_agent_for_ui" in source
    assert "await self._start_or_reuse_agent(runtime_instance_id, logger)" in source
