#!/bin/bash

PROJECT="/Users/marianejacob/Library/Mobile Documents/com~apple~CloudDocs/Documents/m87_terminal"
PYTHON="$HOME/.venvs/m87_terminal/bin/python"

cd "$PROJECT" || exit 1
exec "$PYTHON" "$PROJECT/main.py"
