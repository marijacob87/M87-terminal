#!/bin/bash

osascript <<'APPLESCRIPT'
tell application "Finder"
    close every window
end tell

tell application "System Events"
    set appList to name of every application process whose background only is false
end tell

repeat with appName in appList
    set appName to appName as text

    if appName is not "Finder" and appName is not "Terminal" and appName is not "Python" and appName is not "M87 Terminal" then
        try
            tell application appName to quit
        end try
    end if
end repeat
APPLESCRIPT
