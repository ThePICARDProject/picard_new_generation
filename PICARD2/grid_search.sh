#!/usr/bin/env bash
# Wrapper to run the root grid_search.sh from inside PICARD2/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
exec "$PARENT_DIR/grid_search.sh" "$@"
