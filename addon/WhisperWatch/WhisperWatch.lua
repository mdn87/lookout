-- Turns chat logging on at login so whisper_watch.py can read Logs/WoWChatLog.txt, and
-- flashes a raid warning with a sound when the watched player whispers you.
local TARGET = "saalora"

local frame = CreateFrame("Frame")
frame:RegisterEvent("PLAYER_LOGIN")
frame:RegisterEvent("CHAT_MSG_WHISPER")
frame:SetScript("OnEvent", function(_, event, _, sender)
    if event == "PLAYER_LOGIN" then
        if not LoggingChat() then
            LoggingChat(true)
        end
        print("|cff66ccffWhisperWatch|r: chat log on, watching for " .. TARGET)
        return
    end
    if sender and sender:lower():find(TARGET, 1, true) then
        PlaySound(SOUNDKIT.RAID_WARNING, "Master")
        RaidNotice_AddMessage(RaidWarningFrame, sender .. " whispered you", ChatTypeInfo["WHISPER"])
    end
end)
