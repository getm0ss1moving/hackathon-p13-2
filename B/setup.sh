#!/bin/sh
set -eu
B_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$B_DIR"
if command -v uv >/dev/null 2>&1; then
    if [ ! -d .venv ]; then
        uv venv --python "${B_PYTHON:-3.13}" .venv
    fi
    uv pip sync --python .venv/bin/python requirements.txt
else
    if [ ! -d .venv ]; then
        "${B_PYTHON:-python3}" -m venv .venv
    fi
    .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python prepare_data.py
.venv/bin/python check_env.py
