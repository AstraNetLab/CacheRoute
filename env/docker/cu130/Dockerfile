ARG CUDA_VERSION=13.0.0
ARG PYTHON_VERSION=3.12
ARG RUST_TOOLCHAIN=stable

FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu22.04

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG PYTHON_VERSION
ARG RUST_TOOLCHAIN

ENV DEBIAN_FRONTEND=noninteractive
ENV RUSTUP_HOME=/opt/rustup
ENV CARGO_HOME=/opt/cargo
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONNOUSERSITE=1
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:/opt/cargo/bin:${PATH}"
ENV CACHEROUTE_RUNTIME_PROFILE=v1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        software-properties-common \
        ca-certificates \
        curl \
        git \
        git-lfs \
        wget \
        vim \
        nano \
        less \
        tmux \
        unzip \
        build-essential \
        pkg-config \
        cmake \
        ninja-build \
        libssl-dev \
        libnuma-dev \
        libibverbs-dev \
        libcurl4-openssl-dev \
        libhiredis-dev \
        libgl1 \
        ffmpeg \
        net-tools \
        iproute2 \
        iputils-ping \
        iperf \
        htop \
        jq \
        lsof \
        openssh-client && \
    rm -rf /var/lib/apt/lists/*

# Ubuntu 22.04 does not provide Python 3.12 as its default interpreter.
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        "python${PYTHON_VERSION}" \
        "python${PYTHON_VERSION}-dev" \
        "python${PYTHON_VERSION}-venv" \
        "python${PYTHON_VERSION}-tk" && \
    rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install \
        /usr/bin/python3 \
        python3 \
        "/usr/bin/python${PYTHON_VERSION}" \
        1 && \
    python3 -m venv "${VIRTUAL_ENV}"

# Isolate the serving stack from Ubuntu's system Python packages.
RUN python3 -m pip install --no-cache-dir --upgrade \
        "pip<26" \
        "setuptools>=77,<81" \
        wheel \
        uv

# Rust/Cargo are required by instance/resource_agent.
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | \
        sh -s -- -y \
        --profile minimal \
        --default-toolchain "${RUST_TOOLCHAIN}" && \
    chmod -R a+rwX "${RUSTUP_HOME}" "${CARGO_HOME}" && \
    rustc --version && \
    cargo --version

RUN python3 -c "import sys, tkinter; print('python:', sys.executable); print('tkinter:', tkinter.TkVersion)" && \
    ffmpeg -version >/dev/null

COPY constraints.txt /opt/cacheroute/constraints.txt
COPY requirements-dev.txt /opt/cacheroute/requirements-dev.txt

# Install the CUDA 13 PyTorch wheel set before vLLM and LMCache.
RUN python3 -m pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cu130 \
        -c /opt/cacheroute/constraints.txt \
        torch==2.11.0 \
        torchvision==0.26.0 \
        torchaudio==2.11.0

RUN python3 -m pip install --no-cache-dir \
        -c /opt/cacheroute/constraints.txt \
        vllm==0.25.1 \
        lmcache==0.5.2

RUN python3 -m pip install --no-cache-dir \
        -c /opt/cacheroute/constraints.txt \
        -r /opt/cacheroute/requirements-dev.txt

# Validate metadata and real imports. Build steps normally do not receive GPUs,
# so torch.cuda.is_available() is intentionally checked only at container run time.
RUN python3 -m pip check && \
    python3 -c 'from importlib.metadata import version; import sys; import redis; import torch; import torchcodec; import vllm; import lmcache; print("Python serving environment:"); print("python:", sys.version); print("torch:", torch.__version__); print("torch CUDA:", torch.version.cuda); print("vllm:", version("vllm")); print("lmcache:", version("lmcache")); print("transformers:", version("transformers")); print("redis:", version("redis")); print("torchcodec:", version("torchcodec"))'

WORKDIR /workspace/llm-stack/CacheRoute

CMD ["sleep", "infinity"]
