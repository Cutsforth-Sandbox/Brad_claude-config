#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

case "${1:-}" in
  push)
    [ -z "$(git status --porcelain)" ] || { echo "push: working tree dirty — commit first" >&2; exit 1; }
    [ "$(git symbolic-ref --short HEAD)" = main ] || { echo "push: not on main" >&2; exit 1; }
    git push origin main
    ;;
  pull)
    [ "$(git symbolic-ref --short HEAD)" = main ] || { echo "pull: not on main" >&2; exit 1; }
    git fetch origin main
    git merge --ff-only FETCH_HEAD || {
      echo "pull: local and origin have diverged — inspect with:" >&2
      echo "  git log --oneline main..FETCH_HEAD" >&2
      exit 1
    }
    ;;
  *)
    echo "usage: sync-config.sh push|pull" >&2
    exit 1
    ;;
esac
