-- Just enough of the WoW client API to load Lookout and fire events at it in tests.
T = { sent = {}, screen = {}, printed = {}, timers = {}, frames = {}, filters = {}, afk = false,
      now = 100, logging = false, bg = {}, waypoints = {} }

local function noop() end
local function widget(kind)
    local obj = { events = {}, scripts = {}, shown = true, text = "" }
    function obj:RegisterEvent(event) self.events[event] = true end
    function obj:SetScript(name, fn) self.scripts[name] = fn end
    function obj:Show() self.shown = true end
    function obj:Hide() self.shown = false end
    function obj:IsShown() return self.shown end
    function obj:SetText(text) self.text = text end
    function obj:GetStringHeight() return 12 end
    function obj:CreateFontString() return widget("FontString") end
    function obj:CreateTexture() return widget("Texture") end
    function obj:GetEffectiveScale() return 1 end
    function obj:GetHeight() return 768 end
    function obj:SetScale(value) self.scale = value end
    return setmetatable(obj, { __index = function() return noop end })
end

function CreateFrame(kind)
    local frame = widget(kind)
    T.frames[#T.frames + 1] = frame
    return frame
end

function T.fire(event, ...)
    for _, frame in ipairs(T.frames) do
        if frame.events[event] and frame.scripts.OnEvent then frame.scripts.OnEvent(frame, event, ...) end
    end
end

function T.flush()
    local due = T.timers
    T.timers = {}
    for _, fn in ipairs(due) do fn() end
end

UIParent = widget("Frame")
RaidWarningFrame = {}
SOUNDKIT = { RAID_WARNING = 8959 }
ChatTypeInfo = setmetatable({}, { __index = function() return {} end })
SlashCmdList = {}
C_Timer = { After = function(_, fn) T.timers[#T.timers + 1] = fn end }

function UnitName() return "Yizzity" end
function UnitIsAFK() return T.afk end
function GetTime() return T.now end
function Screenshot() T.screenshots = (T.screenshots or 0) + 1 end
function GetPhysicalScreenSize() return 3840, 2160 end
function LoggingChat(on) if on ~= nil then T.logging = on end return T.logging end
function PlaySound() end
function RaidNotice_AddMessage(_, text) T.screen[#T.screen + 1] = text end
function print(text) T.printed[#T.printed + 1] = text end
function ChatFrame_AddMessageEventFilter(event, fn) T.filters[event] = fn end
function GetBattlefieldStatus(i) return T.bg[i], "Warsong Gulch" end
function SendChatMessage(msg, kind, _, target)
    T.sent[#T.sent + 1] = { msg = msg, kind = kind, target = target }
    if kind == "AFK" then T.afk = true end
end

-- Modern quest log. T.quests = { { header = "Zone" } or { id, title, complete, objectives = { {text, finished} } } }
T.quests = {}
C_QuestLog = {
    GetNumQuestLogEntries = function() return #T.quests end,
    GetInfo = function(i)
        local q = T.quests[i]
        if q.header then return { title = q.header, isHeader = true } end
        return { title = q.title, questID = q.id }
    end,
    GetQuestObjectives = function(id)
        for _, q in ipairs(T.quests) do if q.id == id then return q.objectives end end
    end,
    IsComplete = function(id)
        for _, q in ipairs(T.quests) do if q.id == id then return q.complete end end
    end,
}

function T.slash(text) SlashCmdList.LOOKOUT(text) end

function T.load(ns, name, src)
    local chunk = assert(loadstring(src, "@" .. name))
    chunk("Lookout", ns)
end
