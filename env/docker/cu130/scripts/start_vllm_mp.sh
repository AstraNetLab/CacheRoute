#!/usr/bin/env bash
set -euo pipefail

# CacheRoute v1 / vLLM 0.25.1 startup with LMCacheMPConnector.
# Run LMCache MP first, then:
#   bash env/docker/cu130/scripts/start_vllm_mp.sh

export CACHEROUTE_RUNTIME_PROFILE="${CACHEROUTE_RUNTIME_PROFILE:-v1}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}"
export MODEL_DIR="${MODEL_DIR:-/workspace/llm-stack/models/LLM-Research/Meta-Llama-3-70B-Instruct}"
export PYTHONHASHSEED="${PYTHONHASHSEED:-0}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"

# The validated v1 path does not use the legacy YAML/offloading interface.
unset LMCACHE_CONFIG_FILE
unset PYTORCH_CUDA_ALLOC_CONF

SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-llama3-70b}"
VLLM_HOST="${VLLM_HOST:-0.0.0.0}"
VLLM_PORT="${VLLM_PORT:-8000}"
TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-8}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.75}"
MODEL_DTYPE="${MODEL_DTYPE:-auto}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-4096}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-8}"
MAX_NUM_BATCHED_TOKENS="${MAX_NUM_BATCHED_TOKENS:-16384}"

LMCACHE_MP_CONNECT_HOST="${LMCACHE_MP_CONNECT_HOST:-tcp://127.0.0.1}"
LMCACHE_MP_PORT="${LMCACHE_MP_PORT:-5555}"

if [[ -n "${VLLM_KV_TRANSFER_CONFIG_JSON:-}" ]]; then
  KV_TRANSFER_CONFIG_JSON="${VLLM_KV_TRANSFER_CONFIG_JSON}"
else
  KV_TRANSFER_CONFIG_JSON="$(printf '{"kv_connector":"LMCacheMPConnector","kv_connector_module_path":"lmcache.integration.vllm.lmcache_mp_connector","kv_role":"kv_both","kv_connector_extra_config":{"lmcache.mp.host":"%s","lmcache.mp.port":%s}}' \
    "${LMCACHE_MP_CONNECT_HOST}" "${LMCACHE_MP_PORT}")"
fi

printf '[CacheRoute v1] starting vLLM with LMCacheMPConnector\n'
printf '  profile: %s\n' "${CACHEROUTE_RUNTIME_PROFILE}"
printf '  model: %s (%s)\n' "${MODEL_DIR}" "${SERVED_MODEL_NAME}"
printf '  GPUs / TP: %s / %s\n' "${CUDA_VISIBLE_DEVICES}" "${TENSOR_PARALLEL_SIZE}"
printf '  LMCache MP: %s:%s\n' "${LMCACHE_MP_CONNECT_HOST}" "${LMCACHE_MP_PORT}"

exec vllm serve "${MODEL_DIR}" \
  --served-model-name "${SERVED_MODEL_NAME}" \
  --host "${VLLM_HOST}" \
  --port "${VLLM_PORT}" \
  --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}" \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
  --dtype "${MODEL_DTYPE}" \
  --max-model-len "${MAX_MODEL_LEN}" \
  --max-num-seqs "${MAX_NUM_SEQS}" \
  --max-num-batched-tokens "${MAX_NUM_BATCHED_TOKENS}" \
  --disable-hybrid-kv-cache-manager \
  --no-enable-prefix-caching \
  --kv-transfer-config "${KV_TRANSFER_CONFIG_JSON}" \
  --kv-cache-metrics \
  "$@"
