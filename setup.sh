#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PROJECT_DIR"
if command -v uv >/dev/null 2>&1; then
    if [ ! -d .venv ]; then
        uv venv --python "${RUNBOOK_PYTHON:-3.13}" .venv
    fi
    uv pip sync --python .venv/bin/python requirements.txt
else
    if [ ! -d .venv ]; then
        "${RUNBOOK_PYTHON:-python3}" -m venv .venv
    fi
    .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python scripts/prepare_data.py
.venv/bin/python scripts/check_env.py
