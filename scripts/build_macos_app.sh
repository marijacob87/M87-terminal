#!/bin/bash

set -eu

PROJECT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON="${M87_PYTHON:-$HOME/.venvs/m87_terminal/bin/python}"
APP="$PROJECT/dist/M87 Terminal.app"
TEMP_DIR="$(mktemp -d /tmp/m87_macos_app.XXXXXX)"
BUILD_APP="$TEMP_DIR/M87 Terminal.app"
CONTENTS="$BUILD_APP/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
EXECUTABLE="$MACOS/M87 Terminal"

trap 'rm -rf "$TEMP_DIR"' EXIT

if [ ! -x "$PYTHON" ]; then
    echo "[ERRO] Python do M87 não encontrado: $PYTHON" >&2
    exit 1
fi

if [ -e "$APP" ]; then
    echo "[ERRO] O aplicativo já existe: $APP" >&2
    echo "Mova-o ou envie-o para a Lixeira antes de gerar outro." >&2
    exit 1
fi

PYTHON_BASE="$($PYTHON -c 'import sys; print(sys._base_executable)')"
PYTHON_CONFIG="$(dirname "$PYTHON_BASE")/python3.12-config"
if [ ! -x "$PYTHON_CONFIG" ]; then
    echo "[ERRO] python3.12-config não encontrado no ambiente do M87." >&2
    exit 1
fi

mkdir -p "$MACOS" "$RESOURCES"
cp "$PROJECT/assets/m87_icon.icns" "$RESOURCES/m87_icon.icns"
cp "$PROJECT/scripts/macos_Info.plist" "$CONTENTS/Info.plist"

/usr/libexec/PlistBuddy -c "Set :M87ProjectRoot $PROJECT" "$CONTENTS/Info.plist"
/usr/libexec/PlistBuddy -c "Set :M87PythonExecutable $PYTHON" "$CONTENTS/Info.plist"

clang \
    -fobjc-arc \
    $($PYTHON_CONFIG --embed --cflags) \
    -g0 \
    "$PROJECT/scripts/macos_launcher.m" \
    $($PYTHON_CONFIG --embed --ldflags) \
    -framework Foundation \
    -o "$EXECUTABLE"

xattr -cr "$BUILD_APP"
codesign --force --deep --sign - "$BUILD_APP"
mkdir -p "$PROJECT/dist"
ditto "$BUILD_APP" "$APP"

echo "Aplicativo criado em: $APP"
