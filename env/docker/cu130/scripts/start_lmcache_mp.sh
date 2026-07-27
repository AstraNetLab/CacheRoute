#!/usr/bin/env bash
set -euo pipefail

# CacheRoute v1 / LMCache 0.5.2 MP server startup.
# Run with: bash env/docker/cu130/scripts/start_lmcache_mp.sh

export CACHEROUTE_RUNTIME_PROFILE="${CACHEROUTE_RUNTIME_PROFILE:-v1}"
export LMCACHE_LOG_LEVEL="${LMCACHE_LOG_LEVEL:-INFO}"
export PYTHONHASHSEED="${PYTHONHASHSEED:-0}"

# The legacy YAML-based LMCache configuration must not leak into MP mode.
unset LMCACHE_CONFIG_FILE

LMCACHE_INSTANCE_ID="${LMCACHE_INSTANCE_ID:-cacheroute-lmcache-1}"
LMCACHE_MP_HOST="${LMCACHE_MP_HOST:-127.0.0.1}"
LMCACHE_MP_PORT="${LMCACHE_MP_PORT:-5555}"
LMCACHE_HTTP_HOST="${LMCACHE_HTTP_HOST:-127.0.0.1}"
LMCACHE_HTTP_PORT="${LMCACHE_HTTP_PORT:-8080}"
LMCACHE_L1_SIZE_GB="${LMCACHE_L1_SIZE_GB:-80}"
LMCACHE_CHUNK_SIZE="${LMCACHE_CHUNK_SIZE:-256}"
LMCACHE_HASH_ALGORITHM="${LMCACHE_HASH_ALGORITHM:-sha256_cbor}"
LMCACHE_EVICTION_POLICY="${LMCACHE_EVICTION_POLICY:-LRU}"
LMCACHE_MAX_WORKERS="${LMCACHE_MAX_WORKERS:-8}"
LMCACHE_L2_STORE_POLICY="${LMCACHE_L2_STORE_POLICY:-default}"

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
LMCACHE_L2_WORKERS="${LMCACHE_L2_WORKERS:-8}"

if [[ -n "${LMCACHE_L2_ADAPTER_JSON:-}" ]]; then
  L2_ADAPTER_JSON="${LMCACHE_L2_ADAPTER_JSON}"
else
  L2_ADAPTER_JSON="$(printf '{"type":"resp","host":"%s","port":%s,"num_workers":%s}' \
    "${REDIS_HOST}" "${REDIS_PORT}" "${LMCACHE_L2_WORKERS}")"
fi

printf '[CacheRoute v1] starting LMCache MP server\n'
printf '  profile: %s\n' "${CACHEROUTE_RUNTIME_PROFILE}"
printf '  MP endpoint: %s:%s\n' "${LMCACHE_MP_HOST}" "${LMCACHE_MP_PORT}"
printf '  HTTP endpoint: %s:%s\n' "${LMCACHE_HTTP_HOST}" "${LMCACHE_HTTP_PORT}"
printf '  RESP L2: %s:%s\n' "${REDIS_HOST}" "${REDIS_PORT}"
printf '  chunk/hash: %s / %s\n' "${LMCACHE_CHUNK_SIZE}" "${LMCACHE_HASH_ALGORITHM}"

exec lmcache server \
  --instance-id "${LMCACHE_INSTANCE_ID}" \
  --host "${LMCACHE_MP_HOST}" \
  --port "${LMCACHE_MP_PORT}" \
  --http-host "${LMCACHE_HTTP_HOST}" \
  --http-port "${LMCACHE_HTTP_PORT}" \
  --l1-size-gb "${LMCACHE_L1_SIZE_GB}" \
  --chunk-size "${LMCACHE_CHUNK_SIZE}" \
  --hash-algorithm "${LMCACHE_HASH_ALGORITHM}" \
  --eviction-policy "${LMCACHE_EVICTION_POLICY}" \
  --max-workers "${LMCACHE_MAX_WORKERS}" \
  --l2-store-policy "${LMCACHE_L2_STORE_POLICY}" \
  --l2-adapter "${L2_ADAPTER_JSON}" \
  "$@"
