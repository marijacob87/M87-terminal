#!/bin/bash

PROJECT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON="${M87_PYTHON:-$HOME/.venvs/m87_terminal/bin/python}"

cd "$PROJECT" || exit 1

if [ ! -x "$PYTHON" ]; then
    echo "[ERRO] Python do M87 não encontrado: $PYTHON" >&2
    exit 1
fi

exec "$PYTHON" "$PROJECT/main.py"
