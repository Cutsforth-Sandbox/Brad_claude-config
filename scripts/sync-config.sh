#!/usr/bin/env bash
set -euo pipefail

if findmnt -T /mnt/hgfs/VMShare-config >/dev/null 2>&1; then
    SHARE=/mnt/hgfs/VMShare-config; SIDE=vm; OTHER=win
elif [ -n "${OneDrive:-}" ]; then
    SHARE=/c/VMShare-config; SIDE=win; OTHER=vm
else
    echo "sync-config: can't tell which machine this is" >&2
    exit 1
fi

cd "$(dirname "${BASH_SOURCE[0]}")/.."

case "${1:-}" in
  push)
    [ -z "$(git status --porcelain)" ] || { echo "push: working tree dirty — commit first" >&2; exit 1; }
    [ "$(git symbolic-ref --short HEAD)" = main ] || { echo "push: not on main" >&2; exit 1; }
    tmp="$SHARE/.claude-config.from-$SIDE.tmp"
    dest="$SHARE/claude-config.from-$SIDE.bundle"
    git bundle create "$tmp" --all
    git bundle verify "$tmp"
    mv "$tmp" "$dest"
    echo "pushed: $dest"
    ;;
  pull)
    [ "$(git symbolic-ref --short HEAD)" = main ] || { echo "pull: not on main" >&2; exit 1; }
    src="$SHARE/claude-config.from-$OTHER.bundle"
    [ -f "$src" ] || { echo "pull: no bundle at $src" >&2; exit 1; }
    git fetch "$src" main
    git merge --ff-only FETCH_HEAD
    ;;
  *)
    echo "usage: sync-config.sh push|pull" >&2
    exit 1
    ;;
esac
