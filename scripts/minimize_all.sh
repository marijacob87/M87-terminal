#!/bin/bash

osascript <<'APPLESCRIPT'
tell application "Finder"
    close every window
end tell

tell application "System Events"
    set appList to every application process whose background only is false
    repeat with theApp in appList
        try
            set visible of theApp to false
        end try
    end repeat
end tell
APPLESCRIPT
