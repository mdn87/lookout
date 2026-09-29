-- Explicit one-shot experiment, separate from normal alert delivery.
local _, ns = ...
local frame, busy
local textures = {}

ns.commands.qrtest = function(code)
    if not code:match("^[a-zA-Z0-9%-]+$") or #code > 32 then
        ns.say("Usage: /lo qrtest <test-code, up to 32 letters/digits/hyphens>")
        return
    end
    if busy then ns.say("Screenshot test already running."); return end
    local ok, matrix = ns.qrcode("LOOKOUT-PROBE-1:" .. code)
    if not ok then ns.say("QR encoding failed."); return end
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
            if not busy then return end
            busy = nil
            frame:Hide()
            ns.say(event == "SCREENSHOT_SUCCEEDED" and "Screenshot test saved." or "Screenshot test failed.")
        end)
    end
    for _, texture in ipairs(textures) do texture:Hide() end
    local module = 6
    local size = (#matrix + 8) * module
    -- WoW's root UI units are not physical pixels, even at effective scale 1.
    local _, screenHeight = GetPhysicalScreenSize()
    frame:SetScale(UIParent:GetHeight() / screenHeight)
    frame:SetSize(size, size)
    frame:ClearAllPoints()
    frame:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", 16, 16)
    local used = 0
    for x = 1, #matrix do
        for y = 1, #matrix do
            if matrix[x][y] > 0 then
                used = used + 1
                local texture = textures[used] or frame:CreateTexture(nil, "ARTWORK")
                textures[used] = texture
                texture:SetColorTexture(0, 0, 0, 1)
                texture:SetSize(module, module)
                texture:ClearAllPoints()
                texture:SetPoint("TOPLEFT", frame, "TOPLEFT", (x + 3) * module, -(y + 3) * module)
                texture:Show()
            end
        end
    end
    local run = {}
    busy = run
    frame:Show()
    C_Timer.After(1, function() if busy == run then Screenshot() end end)
    C_Timer.After(10, function()
        if busy == run then
            busy = nil
            frame:Hide()
            ns.say("Screenshot test timed out.")
        end
    end)
end
