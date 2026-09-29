-- Lookout alerts: watched players, chat keywords, messages while you're away, group
-- invites, queue pops and ready checks.
local _, ns = ...

local PUBLIC = {
    CHAT_MSG_CHANNEL = "channel", CHAT_MSG_SAY = "say", CHAT_MSG_YELL = "yell",
    CHAT_MSG_GUILD = "guild", CHAT_MSG_OFFICER = "officer",
    CHAT_MSG_PARTY = "party", CHAT_MSG_PARTY_LEADER = "party",
    CHAT_MSG_RAID = "raid", CHAT_MSG_RAID_LEADER = "raid",
    CHAT_MSG_INSTANCE_CHAT = "instance", CHAT_MSG_INSTANCE_CHAT_LEADER = "instance",
}

local function watched(sender)
    return LookoutDB.names[ns.baseName(sender)]
end

local function keyword(msg)
    local lower = ns.plain(msg):lower()
    for word in pairs(LookoutDB.words) do
        if lower:find(word, 1, true) then return word end
    end
end

local function mentionsMe(msg)
    return ns.plain(msg):lower():find(ns.me(), 1, true) ~= nil
end

local function fromMe(msg, sender)
    return ns.isOwnSignal(msg) or ns.baseName(sender) == ns.me()
end

local function publicChat(where, msg, sender)
    if fromMe(msg, sender) then return end
    local who = ns.baseName(sender)
    if watched(sender) then
        return ns.emit("seen", sender .. " in " .. where .. ": " .. msg, who)
    end
    local word = keyword(msg)
    if word then
        return ns.emit("keyword", sender .. " said " .. word .. ": " .. msg, word)
    end
    if UnitIsAFK("player") and mentionsMe(msg) then
        ns.emit("afk", sender .. " mentioned you: " .. msg, who)
    end
end

local handlers = {}

for event, label in pairs(PUBLIC) do
    handlers[event] = function(msg, sender, _, channel)
        local where = (event == "CHAT_MSG_CHANNEL" and channel and channel ~= "") and channel or label
        publicChat(where, msg, sender)
    end
end

handlers.CHAT_MSG_WHISPER = function(msg, sender)
    if fromMe(msg, sender) then return end
    local who = ns.baseName(sender)
    if watched(sender) then
        return ns.emit("whisper", sender .. ": " .. msg, who)
    end
    if UnitIsAFK("player") then
        return ns.emit("afk", sender .. " whispered: " .. msg, who)
    end
    local word = keyword(msg)
    if word then ns.emit("keyword", sender .. " whispered " .. word .. ": " .. msg, word) end
end

-- The sender of a Battle.net whisper is a protected string addons can't read.
handlers.CHAT_MSG_BN_WHISPER = function(msg)
    if UnitIsAFK("player") then ns.emit("afk", "Battle.net whisper: " .. msg, "battlenet") end
end

handlers.PARTY_INVITE_REQUEST = function(inviter)
    ns.emit("invite", tostring(inviter) .. " invited you to a group", inviter)
end

handlers.LFG_PROPOSAL_SHOW = function()
    ns.emit("queue", "Dungeon group found - accept now", "lfg")
end

handlers.UPDATE_BATTLEFIELD_STATUS = function(index)
    if not (GetBattlefieldStatus and index) then return end
    local status, map = GetBattlefieldStatus(index)
    if status == "confirm" then
        ns.emit("queue", tostring(map or "Battleground") .. " is ready - enter now", "bg" .. index)
    end
end

handlers.READY_CHECK = function(initiator)
    ns.emit("readycheck", tostring(initiator) .. " started a ready check", "")
end

local frame = CreateFrame("Frame")
local events = {}
for event in pairs(handlers) do events[#events + 1] = event end
ns.listen(frame, events)
frame:SetScript("OnEvent", function(_, event, ...)
    if LookoutDB then handlers[event](...) end
end)
