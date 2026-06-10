-- Accept an incoming FaceTime call if one is ringing.
-- Prints "answered" if a call was accepted, "idle" otherwise.
-- Requires: System Settings > Privacy & Security > Accessibility for the
-- process running Hearth (Terminal / launchd context).

tell application "System Events"
    if not (exists process "FaceTime") then
        return "idle"
    end if
    tell process "FaceTime"
        try
            -- The incoming-call notification exposes an Accept button.
            repeat with w in windows
                if exists (button "Accept" of w) then
                    click button "Accept" of w
                    return "answered"
                end if
            end repeat
        end try
    end tell
end tell

-- Also check the notification banner path (macOS 14+).
tell application "System Events"
    tell process "NotificationCenter"
        try
            repeat with w in windows
                repeat with b in (buttons of w)
                    if description of b contains "Accept" then
                        click b
                        return "answered"
                    end if
                end repeat
            end repeat
        end try
    end tell
end tell

return "idle"
