#!/bin/bash

DESKTOP="$HOME/Desktop"

# Move tudo do Desktop para a Lixeira pelo Finder
osascript <<'APPLESCRIPT'
tell application "Finder"
    set desktopItems to every item of desktop
    repeat with thisItem in desktopItems
        delete thisItem
    end repeat

    delay 1

    empty trash
end tell
APPLESCRIPT

exit 0