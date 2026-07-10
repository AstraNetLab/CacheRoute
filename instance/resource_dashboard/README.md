# CacheRoute Instance Resource Dashboard

This dashboard is a lightweight validation frontend for the native Instance resource agent. It starts or connects to the Rust agent, fetches resource snapshots, and displays CPU, memory, GPU, network, admission-state, and raw JSON information.

It does **not** integrate with the Scheduler or Proxy control plane yet. It also does not change Proxy forwarding, scheduling, KVCache injection, or existing Instance request behavior.

## Files

```text
instance/resource_dashboard/
├── README.md
├── dashboard_app.py          # local desktop monitor, recommended when a GUI display is available
├── dashboard_server.py       # browser/server fallback for containers, headless servers, or remote use
└── static/
    ├── index.html
    ├── app.js
    └── style.css
```

## 1. Build/check the Rust agent

Run from the CacheRoute repository root:

```bash
cargo check --manifest-path instance/resource_agent/Cargo.toml
```

## 2. Recommended container usage: browser dashboard

For Docker containers and remote machines, the browser dashboard is the most reliable choice. It does not require the container to access the host graphical display.

```bash
python3 instance/resource_dashboard/dashboard_server.py \
  --dashboard-listen 0.0.0.0:9202 \
  --agent-listen 127.0.0.1:9201 \
  --sample-interval-ms 1000 \
  --instance-id hp_127.0.0.1:9001
```

Then open this address in the **host browser**:

```text
http://127.0.0.1:9202
```

If the container uses `--network host`, the address above should work directly. If the container does not use host networking, expose the dashboard port when starting the container:

```bash
-p 9202:9202
```

The browser dashboard exposes:

```bash
curl -sS http://127.0.0.1:9202/api/health | python3 -m json.tool
curl -sS http://127.0.0.1:9202/api/snapshot | python3 -m json.tool
curl -sS http://127.0.0.1:9202/api/agent/status | python3 -m json.tool
```

It also supports:

```bash
curl -sS -X POST http://127.0.0.1:9202/api/agent/start | python3 -m json.tool
curl -sS -X POST http://127.0.0.1:9202/api/agent/stop | python3 -m json.tool
```

## 3. Desktop window usage

The desktop dashboard opens a small local Tkinter window:

```bash
python3 instance/resource_dashboard/dashboard_app.py \
  --agent-listen 127.0.0.1:9201 \
  --sample-interval-ms 1000 \
  --instance-id hp_127.0.0.1:9001
```

It auto-starts the Rust resource agent unless `--no-auto-start` is used.

By default, it starts the agent with:

```bash
cargo run --manifest-path instance/resource_agent/Cargo.toml -- \
  --listen 127.0.0.1:9201 \
  --sample-interval-ms 1000 \
  --instance-id hp_127.0.0.1:9001
```

Use `--no-auto-start` if you want to start the agent yourself.

## 4. Why a container may not open a desktop window

Having a physical monitor on the host machine is not enough. A Docker container cannot automatically access the host graphical display. If the container does not have the `DISPLAY` environment variable and the X11 socket mounted, Tkinter will fail with an error such as:

```text
no display name and no $DISPLAY environment variable
```

In this case, either use the browser dashboard in Section 2, or start the container with X11 forwarding enabled.

### X11 example on Linux hosts

On the host machine, allow local Docker clients to access the X server:

```bash
xhost +local:docker
```

Start the container with `DISPLAY` and the X11 Unix socket mounted:

```bash
sudo docker run --gpus all -it \
  --name cacheroute-dev \
  --network host \
  --ipc=host \
  --shm-size=64g \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  --memory=0 \
  --memory-swap=0 \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v /llm-stack:/workspace/llm-stack \
  basic-cu128 bash
```

Inside the container, verify:

```bash
echo $DISPLAY
python3 - <<'EOF'
import tkinter
print("tkinter: ok")
EOF
```

Then run `dashboard_app.py` again.

### WSLg or desktop-capable environments

If you use WSLg or another desktop-capable environment, make sure the container inherits the correct display variables and socket mounts from that environment. If this is inconvenient, use the browser dashboard fallback.

## 5. Validate direct Rust agent endpoint

```bash
curl -sS http://127.0.0.1:9201/healthz
curl -sS http://127.0.0.1:9201/v1/resource/snapshot | python3 -m json.tool
```

A valid snapshot includes:

```text
schema_version
timestamp_ms
devices.cpu
devices.memory
devices.network
devices.gpu, optional
capacity_hint.admission_state
```

## Troubleshooting

### `cargo: command not found`

Use the CacheRoute Docker image built from `env/docker/Dockerfile`, or install Rust manually.

### `ModuleNotFoundError: No module named 'tkinter'`

Install Tkinter as a system package. It should **not** be added to `requirements.txt`.

For Python 3.12:

```bash
apt-get update
apt-get install -y python3.12-tk
```

For the system default Python:

```bash
apt-get update
apt-get install -y python3-tk
```

### Desktop window does not open

If the error mentions `$DISPLAY`, the container has no graphical display access. Use the browser dashboard, or start the container with X11 forwarding as described above.

### Dashboard starts but snapshot is unavailable

Check whether the agent is reachable:

```bash
curl -sS http://127.0.0.1:9201/healthz
```

### GPU list is empty

Check whether the container can run:

```bash
nvidia-smi
```

Make sure the container was started with `--gpus all`.

### Port is already in use

Change ports with:

```bash
--agent-listen 127.0.0.1:<port>
--dashboard-listen 0.0.0.0:<port>
```

## Dashboard API

```text
GET  /api/health
GET  /api/snapshot
GET  /api/agent/status
POST /api/agent/start
POST /api/agent/stop
```

## Future Work

1. Report resource snapshots to the Proxy control plane.
2. Extend `InstancePool` with normalized resource-state fields.
3. Add Instance-side queue and KVCache block metrics.
4. Replace `nvidia-smi` polling with NVML-based GPU collection.
5. Support multiple Instances in one dashboard.
