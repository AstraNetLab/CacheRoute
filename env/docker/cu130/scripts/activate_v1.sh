#!/usr/bin/env bash

# Source this file in every terminal that starts a modern CacheRoute component:
#   source env/docker/cu130/scripts/activate_v1.sh

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  printf 'This script must be sourced, not executed.\n' >&2
  printf 'Run: source env/docker/cu130/scripts/activate_v1.sh\n' >&2
  exit 2
fi

_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
_REPO_ROOT="$(cd -- "${_SCRIPT_DIR}/../../../.." && pwd)"

export CACHEROUTE_RUNTIME_PROFILE=v1
export PYTHONHASHSEED="${PYTHONHASHSEED:-0}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"

case ":${PYTHONPATH:-}:" in
  *":${_REPO_ROOT}:"*) ;;
  *) export PYTHONPATH="${_REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" ;;
esac

# The modern MP path must not inherit legacy LMCache/vLLM settings.
unset LMCACHE_CONFIG_FILE
unset PYTORCH_CUDA_ALLOC_CONF

printf '[CacheRoute v1] environment activated\n'
printf '  repository: %s\n' "${_REPO_ROOT}"
printf '  profile: %s\n' "${CACHEROUTE_RUNTIME_PROFILE}"
printf '  PYTHONPATH: %s\n' "${PYTHONPATH}"
printf '  PYTHONHASHSEED / OMP_NUM_THREADS: %s / %s\n' \
  "${PYTHONHASHSEED}" "${OMP_NUM_THREADS}"

unset _SCRIPT_DIR _REPO_ROOT
