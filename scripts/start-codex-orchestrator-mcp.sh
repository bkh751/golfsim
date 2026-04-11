#!/bin/zsh
set -euo pipefail

export GOLFSIM_REPO_ROOT="/Users/user/workspace/game/golfsim"
cd /Users/user/workspace/game/golfsim/tools/codex-orchestrator-mcp
exec go run .
