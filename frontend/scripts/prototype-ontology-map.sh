#!/usr/bin/env bash
# PROTOTYPE (branch prototype/ontology-map-d3): `npm run prototype:map`.
# Serves the example Knowledge Graphs from a throwaway copy of .stetiq/examples.db on
# port 5057, and the dev UI (which shows the variant switcher) on Vite's port.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
repo="$(git -C "$here" rev-parse --show-toplevel)"
main="$(git -C "$here" worktree list --porcelain | awk 'NR==1{print $2}')"
db_src="${STETIQ_PROTOTYPE_DB:-$main/.stetiq/examples.db}"
db="$here/node_modules/.cache/PROTOTYPE-wipe-me-examples.db"
mkdir -p "$(dirname "$db")"
cp "$db_src" "$db"
(cd "$repo" && uv run stetiq ui --tracking-uri "sqlite:///$db" --port 5057) &
api=$!
trap 'kill $api 2>/dev/null' EXIT
echo "Open: http://localhost:5173/ui/kg/scholar-kg/versions/5/ontology?variant=A"
STETIQ_API=http://127.0.0.1:5057 npx vite
