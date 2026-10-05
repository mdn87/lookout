-- Lookout core: saved settings, slash commands and the alert pipeline.
--
-- An alert always shows on screen. For kinds set to "phone" it also goes to the Lookout
-- companion. Addons can't reach the network or write files while you play, so there are
-- two ways out of the game:
--   screenshot (default): a QR code in a screenshot, see Screenshot.lua.
--   chat: a whisper to yourself ("LOOKOUT :: <character> :: <kind> :: <text>") that the game
--         writes to Logs/WoWChatLog.txt. Forever beta 1.60.1.70009 only writes it at logout.
local ADDON, ns = ...

ns.DEFAULT_ALERTS = {
    whisper = "phone", seen = "phone", keyword = "phone", invite = "phone", queue = "phone",
    readycheck = "phone", afk = "phone", quest = "screen", test = "phone",
}
ns.commands = {}   -- extra slash commands from the other files, by first word
ns.onReady = {}    -- functions to run at PLAYER_LOGIN, once settings are loaded

local PREFIX = "LOOKOUT :: "
local MODES = { phone = true, screen = true, off = true }

local function withDefaults(db)
    db.names = db.names or {}
    db.words = db.words or {}
    db.alerts = db.alerts or {}
    for kind, mode in pairs(ns.DEFAULT_ALERTS) do
        if db.alerts[kind] == nil then db.alerts[kind] = mode end
    end
    if db.phone == nil then db.phone = true end
    if db.hideSignals == nil then db.hideSignals = true end
    db.cooldown = db.cooldown or 60
    db.transport = db.transport or "screenshot"
    db.shotGap = db.shotGap or 20
    db.shotsPerHour = db.shotsPerHour or 30
    return db
end

function ns.say(text)
    print("|cff66ccffLookout|r: " .. text)
end

-- Chat text with links, textures and colour codes reduced to plain words. "|" is the chat
-- escape character and the server rejects a message that misuses it.
function ns.plain(text)
    text = tostring(text or "")
    text = text:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")
    text = text:gsub("|H.-|h(.-)|h", "%1"):gsub("|T.-|t", ""):gsub("|A.-|a", ""):gsub("|K.-|k", "?")
    text = text:gsub("|", "/")
    return text
end

-- "Saalora-Zephras" and "saalora" both become "saalora".
function ns.baseName(name)
    name = tostring(name or "")
    return (name:match("^([^%-]+)") or name):lower()
end

function ns.me()
    return ns.baseName(UnitName("player"))
end

function ns.isOwnSignal(msg)
    return type(msg) == "string" and msg:sub(1, #PREFIX) == PREFIX
end

function ns.listen(frame, events)
    for _, event in ipairs(events) do
        pcall(frame.RegisterEvent, frame, event)   -- an event this client lacks is skipped
    end
end

-- Sending a chat message can clear your away flag. Put it back so later whispers still
-- count as arriving while you were away. Unverified: whether a whisper to yourself clears it.
local function keepAway()
    C_Timer.After(1, function()
        if not UnitIsAFK("player") then SendChatMessage("", "AFK") end
    end)
end

local lastSent = {}

-- Hand one message to the companion by the configured transport.
function ns.send(kind, text)
    if LookoutDB.transport == "screenshot" then
        ns.sendShot(kind, text)
        return
    end
    local me, suffix = UnitName("player")
    -- Forever returns a surname as the second value; other clients may return a realm.
    if suffix and suffix ~= "" then me = me .. "-" .. suffix end
    local away = UnitIsAFK("player")
    SendChatMessage((PREFIX .. me .. " :: " .. kind .. " :: " .. text):sub(1, 250), "WHISPER", nil, me)
    if away then keepAway() end
end

-- Raise an alert of one kind. key separates alerts of the same kind (one player, one
-- quest) so each gets its own cooldown. Returns true when the alert went to the phone.
function ns.emit(kind, text, key)
    local db = LookoutDB
    local mode = db.alerts[kind] or "screen"
    if mode == "off" then return false end
    local slot = kind .. ":" .. tostring(key or "")
    local now = GetTime()
    if lastSent[slot] and now - lastSent[slot] < db.cooldown then return false end
    lastSent[slot] = now

    text = ns.plain(text)
    RaidNotice_AddMessage(RaidWarningFrame, text, ChatTypeInfo["RAID_WARNING"])
    PlaySound(SOUNDKIT.RAID_WARNING, "Master")
    if mode ~= "phone" or not db.phone then return false end
    ns.send(kind, text)
    return true
end

-- Where the character is right now, for questions sent to the companion's assistant. Each
-- call is guarded because not every client has every function.
function ns.whereAmI()
    local function get(fn, ...)
        local ok, value = pcall(fn, ...)
        return ok and value and tostring(value) or nil
    end
    local parts = {}
    local level, class = get(UnitLevel, "player"), get(UnitClass, "player")
    parts[#parts + 1] = (UnitName("player") or "?") .. (level and " lvl " .. level or "") .. (class and " " .. class or "")
    parts[#parts + 1] = get(UnitFactionGroup, "player")
    parts[#parts + 1] = get(GetRealmName)
    local zone, sub = get(GetZoneText), get(GetSubZoneText)
    if zone and sub and sub ~= "" and sub ~= zone then zone = zone .. " (" .. sub .. ")" end
    parts[#parts + 1] = zone
    parts[#parts + 1] = get(GetZonePVPInfo)
    local out = {}
    for _, part in ipairs(parts) do
        if part and part ~= "" then out[#out + 1] = part end
    end
    return table.concat(out, ", ")
end

-- "/lo help <question>": the companion asks its assistant and the answer comes back as a
-- phone alert. The character's whereabouts ride along so "where am I" questions work.
local function askAssistant(question)
    local text = ns.plain(question):gsub("[\t\r\n]", " "):sub(1, 110) .. " [" .. ns.whereAmI():sub(1, 85) .. "]"
    ns.send("help", text)
    ns.say("asked the companion; the answer goes to your phone")
end

local function hideSignal(_, _, msg)
    return LookoutDB and LookoutDB.hideSignals and ns.isOwnSignal(msg)
end
ChatFrame_AddMessageEventFilter("CHAT_MSG_WHISPER", hideSignal)
ChatFrame_AddMessageEventFilter("CHAT_MSG_WHISPER_INFORM", hideSignal)

local function sortedKeys(set)
    local out = {}
    for key in pairs(set) do out[#out + 1] = key end
    table.sort(out)
    return #out > 0 and table.concat(out, ", ") or "(none)"
end

local HELP = {
    "/lo add <name>, /lo remove <name>, /lo names - players to watch",
    "/lo word add <text>, /lo word remove <text>, /lo words - chat keywords",
    "/lo alert <kind> phone|screen|off, /lo alerts - where each alert goes",
    "/lo phone on|off, /lo hide on|off, /lo test - phone alerts",
    "/lo transport screenshot|chat, /lo rate [seconds perHour] - how phone alerts leave the game",
    "/lo quests, /lo way [questID], /lo providers - quest helper",
    "/lo help <question> - ask the companion's assistant; the answer goes to your phone",
}

local function onOff(value, label)
    if value ~= "on" and value ~= "off" then return nil end
    ns.say(label .. " " .. value)
    return value == "on"
end

SLASH_LOOKOUT1 = "/lookout"
SLASH_LOOKOUT2 = "/lo"
SlashCmdList.LOOKOUT = function(input)
    local cmd, rest = (input or ""):match("^%s*(%S*)%s*(.-)%s*$")
    cmd = cmd:lower()
    local db = LookoutDB
    if cmd == "add" and rest ~= "" then
        db.names[ns.baseName(rest)] = true
        ns.say("watching " .. rest)
    elseif cmd == "remove" and rest ~= "" then
        db.names[ns.baseName(rest)] = nil
        ns.say("stopped watching " .. rest)
    elseif cmd == "names" then
        ns.say("watching: " .. sortedKeys(db.names))
    elseif cmd == "word" then
        local action, text = rest:match("^(%S+)%s*(.-)$")
        if action == "add" and text ~= "" then
            db.words[text:lower()] = true
            ns.say("keyword added: " .. text)
        elseif action == "remove" and text ~= "" then
            db.words[text:lower()] = nil
            ns.say("keyword removed: " .. text)
        else
            ns.say(HELP[2])
        end
    elseif cmd == "words" then
        ns.say("keywords: " .. sortedKeys(db.words))
    elseif cmd == "alert" then
        local kind, mode = rest:lower():match("^(%S+)%s+(%S+)$")
        if kind and ns.DEFAULT_ALERTS[kind] and MODES[mode] then
            db.alerts[kind] = mode
            ns.say(kind .. " alerts: " .. mode)
        else
            ns.say("kinds: " .. sortedKeys(ns.DEFAULT_ALERTS) .. "; modes: phone, screen, off")
        end
    elseif cmd == "alerts" then
        local parts = {}
        for kind in pairs(ns.DEFAULT_ALERTS) do parts[#parts + 1] = kind .. "=" .. db.alerts[kind] end
        table.sort(parts)
        ns.say(table.concat(parts, ", ") .. (db.phone and "" or " (phone off)"))
    elseif cmd == "phone" then
        local value = onOff(rest, "phone alerts")
        if value ~= nil then db.phone = value end
    elseif cmd == "hide" then
        local value = onOff(rest, "hiding phone signals from chat")
        if value ~= nil then db.hideSignals = value end
    elseif cmd == "test" then
        ns.emit("test", "Lookout test alert", GetTime())
    elseif cmd == "help" and rest ~= "" then
        askAssistant(rest)
    elseif ns.commands[cmd] then
        ns.commands[cmd](rest)
    else
        for _, line in ipairs(HELP) do ns.say(line) end
    end
end

local frame = CreateFrame("Frame")
frame:RegisterEvent("ADDON_LOADED")
frame:RegisterEvent("PLAYER_LOGIN")
frame:SetScript("OnEvent", function(_, event, name)
    if event == "ADDON_LOADED" and name == ADDON then
        LookoutDB = withDefaults(LookoutDB or {})
    elseif event == "PLAYER_LOGIN" then
        if not LoggingChat() then LoggingChat(true) end
        for _, ready in ipairs(ns.onReady) do ready() end
        ns.say("chat log on. /lo for commands.")
    end
end)
