#!/bin/bash
PROJECT="/Users/marianejacob/Library/Mobile Documents/com~apple~CloudDocs/Documents/m87_terminal"
cd "$PROJECT" || exit 1
exec "$PROJECT/.venv/bin/python" "$PROJECT/main.py"
