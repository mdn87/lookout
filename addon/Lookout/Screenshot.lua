-- Phone alerts by screenshot. The addon draws queued alerts as a QR code in the bottom-left
-- corner, takes a screenshot a second later, and hides the code again. The companion watches
-- the Screenshots folder, reads the code and sends the push. The game writes screenshots
-- straight away, unlike the chat log, which Forever beta 1.60.1.70009 holds until logout.
--
-- Screenshots are rate limited: at most one every db.shotGap seconds (URGENT_GAP for alerts
-- that expire in game) and db.shotsPerHour per hour. Alerts raised in between wait in a
-- queue and go out together in the next screenshot.
--
-- Payload, UTF-8, one field per line:
--   LOOKOUT-2 <sequence number>
--   <character>
--   <kind>\t<text>          one line per alert
--   dropped\t<count>        only when the queue overflowed since the last screenshot
local _, ns = ...

local HEADER = "LOOKOUT-2"
local MODULE = 6            -- physical pixels per QR module
local MAX_SIDE = 73         -- modules; with the quiet zone that's 486 pixels, inside the companion's 512 crop
local MAX_BYTES = 360       -- at error correction M this stays within MAX_SIDE
local MAX_TEXT = 200        -- bytes of one alert's text
local MAX_QUEUE = 20
local MAX_TRIES = 3
local URGENT_GAP = 5
local URGENT = { queue = true, readycheck = true, invite = true }

local frame, busy
local textures = {}

local function finish(run, ok)
    if busy ~= run then return end
    busy = nil
    frame:Hide()
    if run.done then run.done(ok) end
end

-- Draw payload as a QR code, take a screenshot a second later, then hide the code.
-- done(ok) runs when the game reports the screenshot saved or failed, or after 10 seconds.
-- Returns false and a reason when nothing was drawn.
function ns.showQR(payload, done)
    if busy then return false, "busy" end
    local ok, matrix = ns.qrcode(payload, 2)
    if not ok then return false, "encode" end
    if #matrix > MAX_SIDE then return false, "size" end
    if not frame then
        frame = CreateFrame("Frame", nil, UIParent)
        frame:SetFrameStrata("TOOLTIP")
        frame:EnableMouse(false)
        local background = frame:CreateTexture(nil, "BACKGROUND")
        background:SetAllPoints()
        background:SetColorTexture(1, 1, 1, 1)
        frame:RegisterEvent("SCREENSHOT_SUCCEEDED")
        frame:RegisterEvent("SCREENSHOT_FAILED")
        frame:SetScript("OnEvent", function(_, event)
            if busy then finish(busy, event == "SCREENSHOT_SUCCEEDED") end
        end)
    end
    for _, texture in ipairs(textures) do texture:Hide() end
    local size = (#matrix + 8) * MODULE
    -- WoW's root UI units are not physical pixels, even at effective scale 1.
    local _, screenHeight = GetPhysicalScreenSize()
    frame:SetScale(UIParent:GetHeight() / screenHeight)
    frame:SetSize(size, size)
    frame:ClearAllPoints()
    frame:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", 16, 16)
    -- One texture per horizontal run of dark modules, not one per module.
    local used = 0
    for y = 1, #matrix do
        local x = 1
        while x <= #matrix do
            if matrix[x][y] > 0 then
                local start = x
                while x <= #matrix and matrix[x][y] > 0 do x = x + 1 end
                used = used + 1
                local texture = textures[used] or frame:CreateTexture(nil, "ARTWORK")
                textures[used] = texture
                texture:SetColorTexture(0, 0, 0, 1)
                texture:SetSize((x - start) * MODULE, MODULE)
                texture:ClearAllPoints()
                texture:SetPoint("TOPLEFT", frame, "TOPLEFT", (start + 3) * MODULE, -(y + 3) * MODULE)
                texture:Show()
            else
                x = x + 1
            end
        end
    end
    local run = { done = done }
    busy = run
    frame:Show()
    C_Timer.After(1, function() if busy == run then Screenshot() end end)
    C_Timer.After(10, function() finish(run, false) end)
    return true
end

-- The outgoing queue.
local queue, shots = {}, {}
local dropped, lastShot, inFlight = 0, nil, nil
local timerDue, timerToken

-- Cut text to at most n bytes without splitting a UTF-8 character.
local function cut(text, n)
    if #text <= n then return text end
    while n > 0 and text:byte(n + 1) and text:byte(n + 1) >= 0x80 and text:byte(n + 1) < 0xC0 do n = n - 1 end
    return text:sub(1, n)
end

local function hasUrgent()
    for _, item in ipairs(queue) do
        if URGENT[item.kind] then return true end
    end
    return false
end

-- Seconds until the next screenshot may be taken; 0 or less means now.
local function wait(now)
    local db = LookoutDB
    while shots[1] and now - shots[1] >= 3600 do table.remove(shots, 1) end
    local gap = hasUrgent() and math.min(URGENT_GAP, db.shotGap) or db.shotGap
    local left = lastShot and lastShot + gap - now or 0
    if #shots >= db.shotsPerHour then left = math.max(left, shots[1] + 3600 - now) end
    return left
end

local function me()
    local name, suffix = UnitName("player")
    -- Forever returns a surname as the second value; other clients may return a realm.
    if suffix and suffix ~= "" then name = name .. "-" .. suffix end
    return name
end

-- Urgent alerts first, then the rest in arrival order, as many as fit.
local function build()
    local db = LookoutDB
    db.shotSeq = (db.shotSeq or 0) + 1
    local lines = { HEADER .. " " .. db.shotSeq, me() }
    local tail = dropped > 0 and ("dropped\t" .. dropped) or nil
    local used = #lines[1] + #lines[2] + 2 + (tail and #tail + 1 or 0)
    local picked, count = {}, 0
    for pass = 1, 2 do
        for _, item in ipairs(queue) do
            if (pass == 1) == (URGENT[item.kind] == true) then
                local line = item.kind .. "\t" .. item.text
                local room = MAX_BYTES - used - 1
                if count == 0 and #line > room then line = cut(line, room) end
                if #line <= room then
                    lines[#lines + 1] = line
                    used = used + #line + 1
                    picked[item] = true
                    count = count + 1
                end
            end
        end
    end
    if tail then lines[#lines + 1] = tail end
    return table.concat(lines, "\n"), picked
end

local flush

local function schedule(delay)
    local due = GetTime() + delay
    if timerDue and timerDue <= due then return end   -- an earlier check is already coming
    local token = {}
    timerDue, timerToken = due, token
    C_Timer.After(delay, function()
        if timerToken ~= token then return end
        timerDue, timerToken = nil, nil
        flush()
    end)
end

flush = function()
    if #queue == 0 or inFlight then return end
    -- The code covers the corner of the screen for a second, so ordinary alerts wait out a
    -- fight you're at the keyboard for. PLAYER_REGEN_ENABLED sends them afterwards.
    if InCombatLockdown() and not UnitIsAFK("player") and not hasUrgent() then return end
    local now = GetTime()
    local left = wait(now)
    if left > 0 then schedule(left) return end
    local payload, picked = build()
    local sentDropped = dropped
    local ok = ns.showQR(payload, function(saved)
        inFlight = nil
        local keep = {}
        for _, item in ipairs(queue) do
            if not picked[item] then
                keep[#keep + 1] = item
            elseif not saved then
                item.tries = item.tries + 1
                if item.tries < MAX_TRIES then keep[#keep + 1] = item end
            end
        end
        queue = keep
        if saved then dropped = dropped - sentDropped end
        flush()
    end)
    if not ok then schedule(1) return end   -- the screenshot test is using the frame
    inFlight = true
    lastShot = now
    shots[#shots + 1] = now
end

-- Queue one alert for the phone.
function ns.sendShot(kind, text)
    text = cut(((text or ""):gsub("[\t\r\n]", " ")), MAX_TEXT)
    queue[#queue + 1] = { kind = kind, text = text, tries = 0 }
    if #queue > MAX_QUEUE then
        for i, item in ipairs(queue) do
            if not URGENT[item.kind] then table.remove(queue, i); break end
        end
        if #queue > MAX_QUEUE then table.remove(queue, 1) end
        dropped = dropped + 1
    end
    flush()
end

function ns.shotStatus()
    return #queue, #shots
end

ns.commands.rate = function(rest)
    local db = LookoutDB
    local gap, perHour = rest:match("^(%d+)%s+(%d+)$")
    if gap then
        db.shotGap = math.min(math.max(tonumber(gap), URGENT_GAP), 3600)
        db.shotsPerHour = math.min(math.max(tonumber(perHour), 1), 360)
    elseif rest ~= "" then
        ns.say("/lo rate <seconds between screenshots> <screenshots per hour>")
        return
    end
    ns.say(("screenshots at most every %ds (%ds for invites, queues and ready checks), %d per hour; %d alerts waiting")
        :format(db.shotGap, math.min(URGENT_GAP, db.shotGap), db.shotsPerHour, #queue))
end

ns.commands.transport = function(rest)
    local db = LookoutDB
    rest = rest:lower()
    if rest == "screenshot" or rest == "chat" then db.transport = rest end
    ns.say("phone alerts go by " .. db.transport .. (rest == "" and " (screenshot or chat)" or ""))
end

local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_REGEN_ENABLED")
events:SetScript("OnEvent", function() flush() end)
