local fps, image, applied

local function update()
    local target = not image and fps or nil
    if target == applied then
        return
    end
    if target then
        mp.commandv("vf", "add", "@display-fps:fps=fps=" .. target)
    else
        mp.commandv("vf", "remove", "@display-fps")
    end
    applied = target
end

-- The fps filter makes still images fail to load, so skip files that have only image video tracks.
mp.add_hook("on_preloaded", 50, function()
    image = nil
    for _, track in ipairs(mp.get_property_native("track-list", {})) do
        if track.type == "video" and image ~= false then
            image = track.image == true
        end
    end
    update()
end)

mp.observe_property("display-fps", "number", function(_, value)
    if value and value > 0 then
        fps = value
        update()
    end
end)
