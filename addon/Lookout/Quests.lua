-- Lookout quest helper: reads the quest log on both API generations, notices finished
-- objectives and quests ready to turn in, and draws a movable progress panel.
local _, ns = ...

local Q = {}
ns.quests = Q

local function modernLog()
    return C_QuestLog and C_QuestLog.GetInfo and C_QuestLog.GetNumQuestLogEntries
        and C_QuestLog.GetQuestObjectives
end

-- The quest log as a list of { id, title, zone, complete, objectives = { {text, done} } }.
function Q.snapshot()
    local list, zone = {}, nil
    if modernLog() then
        for i = 1, C_QuestLog.GetNumQuestLogEntries() do
            local info = C_QuestLog.GetInfo(i)
            if info and info.isHeader then
                zone = info.title
            elseif info and not info.isHidden then
                local quest = { id = info.questID, title = info.title, zone = zone, objectives = {} }
                for _, objective in ipairs(C_QuestLog.GetQuestObjectives(info.questID) or {}) do
                    quest.objectives[#quest.objectives + 1] = { text = objective.text or "", done = objective.finished and true or false }
                end
                quest.complete = (C_QuestLog.IsComplete and C_QuestLog.IsComplete(info.questID)) and true or false
                list[#list + 1] = quest
            end
        end
    else
        for i = 1, GetNumQuestLogEntries() do
            local title, _, _, isHeader, _, isComplete, _, questID = GetQuestLogTitle(i)
            if isHeader then
                zone = title
            elseif title then
                local quest = { id = questID or title, title = title, zone = zone, objectives = {},
                                complete = isComplete == 1 or isComplete == true }
                for j = 1, GetNumQuestLeaderBoards(i) or 0 do
                    local text, _, finished = GetQuestLogLeaderBoard(j, i)
                    quest.objectives[#quest.objectives + 1] = { text = text or "", done = finished and true or false }
                end
                list[#list + 1] = quest
            end
        end
    end
    return list
end

local known   -- questID -> { complete, done = { [objective index] = bool } }; nil until the first read

-- Compare with the previous read. Only a change to a quest seen before raises an alert, so
-- logging in or picking up a quest is quiet.
function Q.diff(list)
    local fresh = {}
    for _, quest in ipairs(list) do
        local before = known and known[quest.id]
        local state = { complete = quest.complete, done = {} }
        for i, objective in ipairs(quest.objectives) do
            state.done[i] = objective.done
            if before and objective.done and not before.done[i] and not quest.complete then
                ns.say(quest.title .. ": " .. objective.text)
            end
        end
        if before and quest.complete and not before.complete then
            ns.emit("quest", quest.title .. " is ready to turn in", quest.id)
        end
        fresh[quest.id] = state
    end
    known = fresh
end

local panel

local function buildPanel()
    panel = CreateFrame("Frame", "LookoutQuestPanel", UIParent, BackdropTemplateMixin and "BackdropTemplate" or nil)
    panel:SetSize(280, 60)
    panel:SetPoint("RIGHT", UIParent, "RIGHT", -40, 80)
    panel:SetMovable(true)
    panel:EnableMouse(true)
    panel:RegisterForDrag("LeftButton")
    panel:SetScript("OnDragStart", panel.StartMoving)
    panel:SetScript("OnDragStop", panel.StopMovingOrSizing)
    if panel.SetBackdrop then
        panel:SetBackdrop({
            bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
            edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
            edgeSize = 12, insets = { left = 3, right = 3, top = 3, bottom = 3 },
        })
        panel:SetBackdropColor(0, 0, 0, 0.7)
    end
    panel.text = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    panel.text:SetPoint("TOPLEFT", 10, -10)
    panel.text:SetWidth(260)
    panel.text:SetJustifyH("LEFT")
    panel:Hide()
end

function Q.render(list)
    if not (panel and panel:IsShown()) then return end
    local lines, zone = {}, false
    for _, quest in ipairs(list) do
        if quest.zone ~= zone then
            zone = quest.zone
            lines[#lines + 1] = "|cffffd100" .. (zone or "Other") .. "|r"
        end
        if quest.complete then
            lines[#lines + 1] = "|cff20ff20" .. quest.title .. " - turn in|r"
        else
            lines[#lines + 1] = quest.title
            for _, objective in ipairs(quest.objectives) do
                lines[#lines + 1] = (objective.done and "   |cff808080" or "   ") .. objective.text .. (objective.done and "|r" or "")
            end
        end
    end
    panel.text:SetText(#lines > 0 and table.concat(lines, "\n") or "No quests")
    panel:SetHeight(panel.text:GetStringHeight() + 20)
end

local pending = false
function Q.refresh()
    if pending then return end
    pending = true
    C_Timer.After(0.3, function()   -- the log fires several updates at once; read it once
        pending = false
        local list = Q.snapshot()
        Q.diff(list)
        Q.render(list)
    end)
end

local function setShown(show)
    if not panel then buildPanel() end
    if show then panel:Show() else panel:Hide() end
    LookoutDB.questPanel = show
    Q.render(Q.snapshot())
end

ns.commands.quests = function()
    setShown(not (panel and panel:IsShown()))
end

table.insert(ns.onReady, function()
    local frame = CreateFrame("Frame")
    ns.listen(frame, { "QUEST_LOG_UPDATE", "QUEST_ACCEPTED", "QUEST_REMOVED", "QUEST_TURNED_IN", "UNIT_QUEST_LOG_CHANGED" })
    frame:SetScript("OnEvent", Q.refresh)
    if LookoutDB.questPanel then setShown(true) end
    Q.refresh()
end)
