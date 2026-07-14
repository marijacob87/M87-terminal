#!/bin/bash

DESKTOP="$HOME/Desktop"
TRASH="$HOME/.Trash"

# Apaga tudo do Desktop diretamente.
# Não passa pela Lixeira.
find "$DESKTOP" \
    -mindepth 1 \
    -maxdepth 1 \
    -exec rm -rf -- {} +

# Esvazia a Lixeira local.
find "$TRASH" \
    -mindepth 1 \
    -maxdepth 1 \
    -exec rm -rf -- {} +

exit 0