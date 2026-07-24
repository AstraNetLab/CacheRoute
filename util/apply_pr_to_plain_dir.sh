#!/usr/bin/env bash
set -euo pipefail

PR="${1:?usage: apply_pr_to_plain_dir.sh <pr_number> [target_dir]}"
TARGET="${2:-/workspace/llm-stack/CacheRoute}"
REPO="${REPO:-https://github.com/AstraNetLab/CacheRoute.git}"
TMP="/tmp/cacheroute_pr_${PR}"
BACKUP="/tmp/cacheroute_backup_pr_${PR}_$(date +%Y%m%d_%H%M%S)"

echo "[Target] $TARGET"
echo "[PR] #$PR"

rm -rf "$TMP"
git clone "$REPO" "$TMP"

cd "$TMP"
git fetch origin "pull/${PR}/head:pr-${PR}" --force
git switch "pr-${PR}"

BASE=$(git merge-base origin/main "pr-${PR}")

echo
echo "[Changed files]"
git diff --name-status "$BASE" "pr-${PR}"

echo
read -r -p "Apply these files to $TARGET ? [y/N] " ans
if [[ ! "$ans" =~ ^[Yy]$ ]]; then
  echo "Canceled."
  exit 0
fi

mkdir -p "$BACKUP"

git diff --name-status "$BASE" "pr-${PR}" | while IFS=$'\t' read -r status path1 path2; do
  case "$status" in
    D*)
      dst="$TARGET/$path1"
      if [ -e "$dst" ]; then
        mkdir -p "$BACKUP/$(dirname "$path1")"
        cp -a "$dst" "$BACKUP/$path1"
        rm -f "$dst"
        echo "[DELETE] $path1"
      fi
      ;;
    R*|C*)
      src_path="$path2"
      dst="$TARGET/$src_path"
      if [ -e "$dst" ]; then
        mkdir -p "$BACKUP/$(dirname "$src_path")"
        cp -a "$dst" "$BACKUP/$src_path"
      fi
      mkdir -p "$(dirname "$dst")"
      cp -a "$TMP/$src_path" "$dst"
      echo "[COPY] $src_path"
      ;;
    *)
      src_path="$path1"
      dst="$TARGET/$src_path"
      if [ -e "$dst" ]; then
        mkdir -p "$BACKUP/$(dirname "$src_path")"
        cp -a "$dst" "$BACKUP/$src_path"
      fi
      mkdir -p "$(dirname "$dst")"
      cp -a "$TMP/$src_path" "$dst"
      echo "[COPY] $src_path"
      ;;
  esac
done

echo
echo "[Done]"
echo "Backup saved to: $BACKUP"
