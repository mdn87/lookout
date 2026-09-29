-- Lookout integrations. Other addons plug in through the global LookoutAPI:
--
--   LookoutAPI.RegisterProvider({ name = "...", locate = function(questID) return mapID, x, y end })
--       A provider knows where a quest's next step is. Lookout asks each one in order.
--   LookoutAPI.Emit(kind, text, key)   raise a Lookout alert
--   LookoutAPI.Quests()                the quest log as Lookout reads it
--
-- Lookout then points the way with TomTom when it's installed, else with the game's own
-- map pin where the client has one.
local _, ns = ...

local providers = {}

LookoutAPI = {
    version = 1,
    Emit = function(kind, text, key) return ns.emit(kind, text, key) end,
    RegisterProvider = function(provider) providers[#providers + 1] = provider end,
    Quests = function() return ns.quests.snapshot() end,
}

-- Modern clients know the next step of most quests themselves.
LookoutAPI.RegisterProvider({
    name = "game",
    locate = function(questID)
        if C_QuestLog and C_QuestLog.GetNextWaypoint then
            local mapID, x, y = C_QuestLog.GetNextWaypoint(questID)
            if mapID and x and y then return mapID, x, y end
        end
    end,
})

local function locate(questID)
    for _, provider in ipairs(providers) do
        local ok, mapID, x, y = pcall(provider.locate, questID)
        if ok and mapID then return mapID, x, y, provider.name end
    end
end

local function pointAt(title, mapID, x, y)
    if TomTom and TomTom.AddWaypoint then
        TomTom:AddWaypoint(mapID, x, y, { title = title, from = "Lookout" })
        return "TomTom"
    end
    if C_Map and C_Map.SetUserWaypoint and UiMapPoint then
        C_Map.SetUserWaypoint(UiMapPoint.CreateFromCoordinates(mapID, x, y))
        if C_SuperTrack and C_SuperTrack.SetSuperTrackedUserWaypoint then
            C_SuperTrack.SetSuperTrackedUserWaypoint(true)
        end
        return "map pin"
    end
end

-- /lo way [questID]: point at that quest's next step, or at the first quest that has one.
ns.commands.way = function(rest)
    local wanted = tonumber(rest)
    for _, quest in ipairs(ns.quests.snapshot()) do
        if not wanted or quest.id == wanted then
            local mapID, x, y, source = locate(quest.id)
            if mapID then
                local how = pointAt(quest.title, mapID, x, y)
                if how then
                    ns.say(("%s: %.1f, %.1f (from %s, shown with %s)"):format(quest.title, x * 100, y * 100, source, how))
                else
                    ns.say(("%s: %.1f, %.1f (from %s; install TomTom for an arrow)"):format(quest.title, x * 100, y * 100, source))
                end
                return
            end
        end
    end
    ns.say("no location known" .. (wanted and (" for quest " .. wanted) or "") .. ". /lo providers lists the sources.")
end

ns.commands.providers = function()
    local names = {}
    for _, provider in ipairs(providers) do names[#names + 1] = provider.name end
    ns.say("location sources: " .. table.concat(names, ", ") .. "; arrow: " .. ((TomTom and "TomTom") or "none"))
end
