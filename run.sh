#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source .env
cd ..
export PYTHONPATH="$(pwd)/backend"
uvicorn backend.app.main:app --host 0.0.0.0 --port 8789 --reload
