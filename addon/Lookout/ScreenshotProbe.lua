-- Explicit one-shot experiment, separate from normal alert delivery.
local _, ns = ...

ns.commands.qrtest = function(code)
    if not code:match("^[a-zA-Z0-9%-]+$") or #code > 32 then
        ns.say("Usage: /lo qrtest <test-code, up to 32 letters/digits/hyphens>")
        return
    end
    local ok, reason = ns.showQR("LOOKOUT-PROBE-1:" .. code, function(saved)
        ns.say(saved and "Screenshot test saved." or "Screenshot test failed or timed out.")
    end)
    if not ok then
        ns.say(reason == "busy" and "Screenshot test already running." or "QR encoding failed.")
    end
end
