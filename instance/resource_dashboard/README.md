# CacheRoute Instance Resource Dashboard

`instance/resource_dashboard/` contains two local frontends for the Rust Instance Resource Agent:

| Mode | Entry point | Recommended use |
|---|---|---|
| Browser | `dashboard_server.py` | Integrated demos, containers, SSH sessions, and headless hosts. |
| Desktop | `dashboard_app.py` | Local machines with Tkinter and an accessible graphical display. |

The Dashboard is an observability and debugging tool. It displays CPU, memory, network, optional GPU metrics, admission state, and raw Resource Agent snapshots. It does not make scheduling decisions and does not modify Proxy forwarding, Scheduler routing, or KVCache injection behavior.

## Recommended integrated mode

For normal Instance demos, start the browser Dashboard through `test/demo_instance.py`:

```bash
python3 test/demo_instance.py \
  --host 127.0.0.1 \
  --port 9001 \
  --ui
```

This single command starts the Instance and, when needed, the local Resource Agent and browser Dashboard.

Default endpoints:

| Component | Default endpoint |
|---|---|
| Instance | `http://127.0.0.1:9001` |
| Resource Agent | `http://127.0.0.1:9201` |
| Browser Dashboard | `http://127.0.0.1:9202` |

Integrated mode always starts `dashboard_server.py` with:

```text
--no-auto-start
```

This prevents the Dashboard from starting a second Resource Agent. `demo_instance.py` remains the sole lifecycle owner of any Agent process it starts.

## Browser-opening behavior

Explicit `--ui` enables automatic browser opening by default:

```bash
python3 test/demo_instance.py --ui
```

For SSH, Docker, CI, root shells, or hosts without a usable desktop browser:

```bash
python3 test/demo_instance.py \
  --ui \
  --no-ui-open-browser
```

`--no-ui-open-browser` does **not** disable the Dashboard. It only disables the attempt to launch a browser. The server still starts and prints its URL.

Disable the integrated Dashboard entirely with:

```bash
python3 test/demo_instance.py --no-ui
```

## CLI and environment configuration

Dashboard CLI options in `demo_instance.py`:

| Option | Description |
|---|---|
| `--ui` / `--no-ui` | Enable or disable integrated Dashboard startup. |
| `--ui-listen HOST:PORT` | Dashboard listen address. Default: `0.0.0.0:9202`. |
| `--ui-open-browser` / `--no-ui-open-browser` | Enable or disable automatic browser opening. |
| `--ui-start-timeout-s SECONDS` | Dashboard readiness timeout. Default: `5`. |

Equivalent environment variables:

```text
INSTANCE_UI_ENABLE
INSTANCE_UI_LISTEN
INSTANCE_UI_OPEN_BROWSER
INSTANCE_UI_START_TIMEOUT_S
```

Precedence is:

```text
explicit CLI option > environment variable > core/config.py default
```

Explicit `--ui` opens the browser by default unless `--no-ui-open-browser` is also supplied. UI enabled only through environment/config uses `INSTANCE_UI_OPEN_BROWSER`.

## Listen address and usable URL

The default listen address is:

```text
0.0.0.0:9202
```

This allows the server to accept connections through any host/container interface. Wildcard addresses are not useful browser destinations, so local health checks and the printed browser URL use:

```text
http://127.0.0.1:9202
```

The same mapping applies to `::` and `[::]` wildcard IPv6 listen addresses.

## SSH access

When the Dashboard runs on a remote machine and listens on loopback, create an SSH tunnel from the local computer:

```bash
ssh -L 9202:127.0.0.1:9202 user@server
```

Then open locally:

```text
http://127.0.0.1:9202
```

Keep `demo_instance.py` running while using the Dashboard.

## Docker access

With `--network host`, open the host URL directly:

```text
http://127.0.0.1:9202
```

Without host networking, publish the port when creating the container:

```bash
-p 9202:9202
```

and bind the Dashboard to all container interfaces:

```bash
python3 test/demo_instance.py \
  --ui \
  --ui-listen 0.0.0.0:9202 \
  --no-ui-open-browser
```

The browser Dashboard does not require Tkinter, `DISPLAY`, or X11.

## Custom ports

Use independent ports to avoid stale local processes:

```bash
python3 test/demo_instance.py \
  --host 127.0.0.1 \
  --port 19001 \
  --resource-agent-listen 127.0.0.1:19201 \
  --resource-agent-url http://127.0.0.1:19201 \
  --resource-agent-sample-interval-ms 1000 \
  --ui \
  --ui-listen 127.0.0.1:19202 \
  --no-ui-open-browser
```

The expected runtime Instance ID is:

```text
hp_127.0.0.1:19001
```

## Validate integrated mode

Keep the Instance process running and use a second terminal.

### Dashboard health

```bash
curl -fsS http://127.0.0.1:9202/api/health \
  | tee /tmp/cacheroute-dashboard-health.json \
  | python3 -m json.tool
```

A valid response includes:

```json
{
  "ok": true,
  "dashboard": "ok",
  "agent": {
    "agent_url": "http://127.0.0.1:9201",
    "sample_interval_ms": 1000,
    "instance_id": "hp_127.0.0.1:9001"
  }
}
```

The integrated launcher validates these fields before declaring the Dashboard ready or reusing an existing Dashboard:

- Dashboard identity;
- Resource Agent URL;
- sample interval;
- runtime Instance ID.

An unrelated HTTP service returning status 200, malformed JSON, or a Dashboard connected to a different Agent is not considered compatible.

### Browser page

```bash
curl -fsS http://127.0.0.1:9202/ | head
```

### Resource Agent

```bash
curl -fsS http://127.0.0.1:9201/healthz | python3 -m json.tool
curl -fsS http://127.0.0.1:9201/v1/resource/snapshot | python3 -m json.tool
```

### Process command

```bash
pgrep -af 'resource_dashboard/dashboard_server.py'
```

The integrated command should contain values equivalent to:

```text
--dashboard-listen 0.0.0.0:9202
--agent-listen 127.0.0.1:9201
--sample-interval-ms 1000
--instance-id hp_127.0.0.1:9001
--no-auto-start
```

### Shutdown cleanup

Press `Ctrl+C` in the `demo_instance.py` terminal, then check:

```bash
! curl -fsS http://127.0.0.1:9202/api/health
! pgrep -af 'resource_dashboard/dashboard_server.py.*9202'
```

`demo_instance.py` terminates only the Dashboard process group it started. A compatible external Dashboard that was reused is not terminated.

## Proxy registration behavior

Dashboard startup is local and is not gated on successful Proxy registration.

When Proxy registration succeeds:

```text
demo_instance.py
  -> start/reuse Resource Agent
  -> start resource reporting when enabled
  -> start Dashboard when enabled
```

When registration fails but UI is enabled:

```text
demo_instance.py
  -> start/reuse Resource Agent for local Dashboard use
  -> skip Proxy resource reporting
  -> start Dashboard
```

This permits local resource inspection while Proxy is unavailable. The Instance logs the registration failure but can continue serving locally.

## Process ownership and failure isolation

Integrated mode follows these ownership rules:

- `demo_instance.py` owns an Agent only when it started that Agent.
- `demo_instance.py` owns a Dashboard only when it started that Dashboard.
- externally reachable compatible processes are reused but not terminated;
- Dashboard readiness, browser-opening, missing-script, bind, or shutdown errors are warnings rather than fatal Instance startup failures;
- shutdown sends `SIGTERM` to the managed Dashboard process group and escalates to `SIGKILL` only after a bounded timeout.

Startup failure logs include the generated command, return code when available, and bounded stdout/stderr tails.

## Standalone browser mode

Use standalone mode for Dashboard component development or when another process owns the Instance/Agent lifecycle:

```bash
python3 instance/resource_dashboard/dashboard_server.py \
  --dashboard-listen 0.0.0.0:9202 \
  --agent-listen 127.0.0.1:9201 \
  --sample-interval-ms 1000 \
  --instance-id hp_127.0.0.1:9001
```

By default, standalone `dashboard_server.py` may start its own Resource Agent. Pass `--no-auto-start` when an Agent is already managed elsewhere:

```bash
python3 instance/resource_dashboard/dashboard_server.py \
  --dashboard-listen 0.0.0.0:9202 \
  --agent-listen 127.0.0.1:9201 \
  --sample-interval-ms 1000 \
  --instance-id hp_127.0.0.1:9001 \
  --no-auto-start
```

For normal CacheRoute demos, prefer `python3 test/demo_instance.py --ui` instead of this standalone command.

## Standalone desktop mode

The Tkinter desktop frontend is available for local GUI environments:

```bash
python3 instance/resource_dashboard/dashboard_app.py \
  --agent-listen 127.0.0.1:9201 \
  --sample-interval-ms 1000 \
  --instance-id hp_127.0.0.1:9001
```

It may auto-start the Resource Agent unless `--no-auto-start` is supplied.

Tkinter is required only for `dashboard_app.py`. Install it as a system package, not a Python package:

```bash
apt-get update
apt-get install -y python3-tk
```

For Python 3.12 distributions, the package may be named `python3.12-tk`.

A Docker container needs access to a host display for desktop mode. A physical monitor alone is not enough. Without `DISPLAY` and X11 access, Tkinter may report:

```text
no display name and no $DISPLAY environment variable
```

Use browser mode unless desktop/X11 testing is specifically required.

## Dashboard API

```text
GET  /api/health
GET  /api/snapshot
GET  /api/agent/status
POST /api/agent/start
POST /api/agent/stop
```

Examples:

```bash
curl -sS http://127.0.0.1:9202/api/health | python3 -m json.tool
curl -sS http://127.0.0.1:9202/api/snapshot | python3 -m json.tool
curl -sS http://127.0.0.1:9202/api/agent/status | python3 -m json.tool
```

The Agent start/stop APIs are primarily useful in standalone Dashboard mode. Integrated mode intentionally keeps Agent lifecycle ownership in `demo_instance.py`.

## Tests

Focused tests for integrated startup, option precedence, health identity validation, browser handling, and process cleanup:

```bash
python3 -m pytest -q test/test_demo_instance_ui.py
```

Syntax validation:

```bash
python3 -m py_compile \
  test/demo_instance.py \
  instance/resource_dashboard/dashboard_server.py
```

CLI smoke check:

```bash
python3 test/demo_instance.py --help
```

## Troubleshooting

### Dashboard URL is printed but no window appears

This is normal when:

- `--no-ui-open-browser` is present;
- the process runs as root without a desktop session;
- the process runs inside Docker;
- the process runs through SSH;
- the machine has no configured default browser.

Open the printed URL manually or use SSH port forwarding.

### Dashboard starts but snapshot is unavailable

Check the Agent directly:

```bash
curl -sS http://127.0.0.1:9201/healthz
```

Verify that Dashboard and Agent use the same address, sample interval, and Instance ID.

### Port already in use

Inspect listeners:

```bash
ss -ltnp | grep -E ':9201|:9202'
```

Use alternate Agent and Dashboard ports when needed.

### `cargo: command not found`

Install Rust/Cargo or use the CacheRoute development image that contains the Rust toolchain.

### GPU list is empty

Run:

```bash
nvidia-smi
```

For Docker, confirm the container was started with GPU access such as `--gpus all`.

## Related documentation

- [`../README.md`](../README.md): Instance lifecycle, configuration, CLI, and resource-reporting path.
- [`../resource_agent/README.md`](../resource_agent/README.md): Rust Resource Agent details.
- [`../../test/README.md`](../../test/README.md): demo entrypoints and local smoke workflows.
- [`../../env/README.md`](../../env/README.md): Docker, Rust, Tkinter, and deployment environment setup.
