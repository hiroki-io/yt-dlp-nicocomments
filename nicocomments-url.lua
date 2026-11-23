local utils = require("mp.utils")

local options = {
    ytdl_path = "",
    fonts_dir = os.getenv("NICOCOMMENTS_FONTS_DIR") or "",
    options = os.getenv("NICOCOMMENTS_OPTIONS") or "",
}
require("mp.options").read_options(options, "nicocomments")

local OWNER_PROPERTY = "user-data/nicocomments/url-script"
local VIDEO_HOSTS = {
    ["nicovideo.jp"] = true,
    ["www.nicovideo.jp"] = true,
    ["sp.nicovideo.jp"] = true,
    ["embed.nicovideo.jp"] = true,
}
-- nico.ms also serves live streams, channels, and other pages that the plugin does not support.
local SHORT_URL_PREFIXES = { [""] = true, sm = true, nm = true, so = true }
local STALE_FILE_SECONDS = 24 * 60 * 60
-- A template of the yt-dlp configuration for one of these types wins over the default template.
local OUTPUT_TYPES = {
    "subtitle",
    "thumbnail",
    "description",
    "annotation",
    "infojson",
    "link",
    "chapter",
    "pl_video",
    "pl_thumbnail",
    "pl_description",
    "pl_infojson",
}
local UNUSED_WRITERS = {
    "--no-write-info-json",
    "--no-write-thumbnail",
    "--no-write-description",
    "--no-write-comments",
    "--no-embed-info-json",
    "--no-embed-thumbnail",
}
local is_windows = package.config:sub(1, 1) == "\\"
local script_directory = utils.split_path(debug.getinfo(1, "S").source:sub(2))
-- Several mpv players can run in one process, for example the windows of IINA.
-- The table stays referenced so that no other script in the process gets its address.
local instance_token = {}
local instance = tostring(instance_token):match("(%x+)$") or "0"
local job
local job_count = 0
local leftover_files = {}

local function is_absolute(path)
    return path:find("^/") or path:find("^%a:[/\\]") or path:find("^\\\\")
end

-- Other users can write to /tmp, so the files go to a directory of this user.
local function find_temporary_directory()
    local cache = mp.command_native({ "expand-path", "~~cache/nicocomments" })
    if cache and is_absolute(cache) then
        return cache
    end
    local windows_directory = is_windows and (os.getenv("TEMP") or os.getenv("TMP"))
    if windows_directory then
        return utils.join_path(windows_directory, "nicocomments")
    end
    return mp.command_native({ "expand-path", "~/.cache/nicocomments" })
end

local temporary_directory = find_temporary_directory()

local function video_url(url)
    local prefixed
    url, prefixed = url:gsub("^ytdl://", "")
    local host, path = url:match("^https?://([^/]+)/(.*)")
    if not host and prefixed > 0 then
        host, path = url:match("^([^/:]+)/(.*)")
    end
    if not host then
        return nil
    end
    host = host:lower()
    if host == "nico.ms" then
        local prefix = path:match("^(%l*)%d")
        return prefix and SHORT_URL_PREFIXES[prefix] and url or nil
    end
    local id = VIDEO_HOSTS[host] and (path:match("^watch/(.*)") or path:match("^shorts/(.*)"))
    -- The Niconico extractor of yt-dlp takes an ID with any two letters before the number.
    return id and (id:find("^%d") or id:find("^%l%l%d")) and url or nil
end

local function fonts_directory()
    if options.fonts_dir ~= "" then
        return options.fonts_dir
    end
    local bundled = utils.join_path(script_directory, "yt_dlp_plugins/postprocessor/_nicocomments/font_data")
    local info = utils.file_info(bundled)
    return info and info.is_dir and bundled or nil
end

-- These are the paths that the ytdl_hook script of mpv searches.
local function ytdl_paths()
    if options.ytdl_path ~= "" then
        return { mp.command_native({ "expand-path", options.ytdl_path }) }
    end
    local found = mp.get_property_native("user-data/mpv/ytdl/path")
    if found and found ~= "" then
        return { found }
    end
    -- read_options warns about each key of ytdl_hook.conf that is not in this table.
    local hook_options = {
        exclude = "",
        include = "",
        try_ytdl_first = false,
        use_manifests = false,
        all_formats = false,
        force_all_formats = true,
        thumbnails = "none",
        ytdl_path = "",
    }
    require("mp.options").read_options(hook_options, "ytdl_hook")
    local paths = {}
    local names = hook_options.ytdl_path ~= "" and hook_options.ytdl_path or "yt-dlp:yt-dlp_x86"
    for name in names:gmatch(is_windows and hook_options.ytdl_path ~= "" and "[^;]+" or "[^:]+") do
        local path = mp.command_native({ "expand-path", name })
        local file = is_windows and not path:lower():find("%.exe$") and path .. ".exe" or path
        paths[#paths + 1] = mp.find_config_file(file) or path
    end
    return paths
end

local function language_order()
    local order = {}
    local count = 0
    for language in (options.options:lower():match("lang=([^;]*)") or ""):gmatch("%a+") do
        count = count + 1
        order[language] = order[language] or count
    end
    return order
end

local function remove_files(paths)
    local remaining = {}
    for _, path in ipairs(paths) do
        -- Windows cannot remove a file while mpv reads it.
        if not os.remove(path) and utils.file_info(path) then
            remaining[#remaining + 1] = path
        end
    end
    return remaining
end

local function written_files(prefix)
    local paths = {}
    for _, name in ipairs(utils.readdir(temporary_directory, "files") or {}) do
        if name:sub(1, #prefix) == prefix then
            paths[#paths + 1] = utils.join_path(temporary_directory, name)
        end
    end
    return paths
end

-- An mpv or yt-dlp process that does not exit normally can leave files.
local function stale_files()
    local paths = {}
    for _, path in ipairs(written_files("")) do
        local _, name = utils.split_path(path)
        local info = name:find("^%d+%-%x+%-%d+%.") and utils.file_info(path)
        if info and os.time() - info.mtime > STALE_FILE_SECONDS then
            paths[#paths + 1] = path
        end
    end
    return paths
end

local function add_tracks(paths)
    local order = language_order()
    local tracks = {}
    for _, path in ipairs(paths) do
        local language = path:match("%.(%a+)%-comments%.ass$")
        if language then
            tracks[#tracks + 1] = { path = path, language = language, order = order[language] or math.huge }
        end
    end
    table.sort(tracks, function(a, b)
        if a.order ~= b.order then
            return a.order < b.order
        end
        return a.path < b.path
    end)
    local added = {}
    for _, track in ipairs(tracks) do
        if mp.commandv("sub-add", track.path, "auto", "comments", track.language) then
            added[#added + 1] = track
        end
    end
    local default_track = options.options:lower():match("defaulttrack=%s*(%w+)")
    local selects = default_track ~= "false" and default_track ~= "no" and default_track ~= "0"
    -- mpv saves a changed sid option for the files that follow and in the watch later file,
    -- so the language selects the track.
    if added[1] and selects then
        mp.set_property_native("file-local-options/slang", { added[1].language })
    end
    return #added > 0
end

local function finish(finished, adds_tracks)
    if finished.finished then
        return
    end
    finished.finished = true
    local paths = written_files(finished.prefix)
    if adds_tracks and not finished.result.killed_by_us then
        for line in (finished.result.stderr or ""):gmatch("[^\r\n]+") do
            mp.msg.warn(line)
        end
        if not add_tracks(paths) then
            mp.msg.warn("Cannot load the comments")
        end
    end
    for _, path in ipairs(remove_files(paths)) do
        leftover_files[#leftover_files + 1] = path
    end
end

local function finish_unused_job()
    if job and job.result then
        finish(job, false)
    end
end

local function run_ytdl(started, paths, index, args)
    args[1] = paths[index]
    mp.command_native_async({ name = "subprocess", args = args, capture_stderr = true }, function(_, result)
        result = result or {}
        if result.error_string == "init" and paths[index + 1] and started == job then
            run_ytdl(started, paths, index + 1, args)
            return
        end
        if result.error_string == "init" and started == job then
            mp.msg.warn("Cannot run yt-dlp: " .. table.concat(paths, ", "))
        end
        started.result = result
        if started.hook then
            finish(started, started == job)
            started.hook:cont()
        elseif started ~= job then
            finish(started, false)
        end
    end)
end

-- mpv can load this script from the scripts directory and from --script at the same time.
local function owns_urls()
    local name = mp.get_script_name()
    local owner = mp.get_property_native(OWNER_PROPERTY)
    if not owner then
        mp.set_property(OWNER_PROPERTY, name)
        return true
    end
    return owner == name
end

-- The ytdl_hook script replaces stream-open-filename at priority 10.
mp.add_hook("on_load", 9, function()
    finish_unused_job()
    job = nil
    local url = video_url(mp.get_property("stream-open-filename", ""))
    local plays = mp.get_property_native("ytdl") and mp.get_property("options/vid") ~= "no"
    if not url or not plays or not owns_urls() then
        return
    end
    local fonts = fonts_directory()
    if fonts then
        mp.set_property("file-local-options/sub-fonts-dir", fonts)
    end

    job_count = job_count + 1
    local started = { prefix = ("%d-%s-%d."):format(utils.getpid(), instance, job_count) }
    job = started
    remove_files(stale_files())
    -- A later mpv process can get the ID of the process that left the files.
    remove_files(written_files(started.prefix))
    local output = utils.join_path(temporary_directory, started.prefix):gsub("%%", "%%%%") .. "%(id)s"
    local postprocessor = "NicoComments:when=video" .. (options.options ~= "" and ";" .. options.options or "")
    local format = mp.get_property("ytdl-format", "")
    local args = { "", "--quiet" }
    -- The plugin lays out the comments for the size of the format that mpv plays.
    -- With the value ytdl, mpv uses the format of the yt-dlp configuration.
    if format ~= "ytdl" then
        args[#args + 1] = "--format"
        args[#args + 1] = format ~= "" and format or "bestvideo*+bestaudio/bestvideo+bestaudio/best"
    end
    -- These options hold the cookies and the proxy that mpv uses to load the video.
    for name, value in pairs(mp.get_property_native("ytdl-raw-options", {})) do
        args[#args + 1] = "--" .. name
        -- An empty proxy turns the proxy off, and the other empty values are flags.
        if value ~= "" or name == "proxy" then
            args[#args + 1] = value
        end
    end
    -- These options follow the raw options because the last value of a yt-dlp option wins.
    -- The yt-dlp configuration can convert the subtitles, and can write other files to other paths.
    local overrides = {
        "--no-simulate",
        "--skip-download",
        "--write-subs",
        "--convert-subs",
        "none",
        "--output",
        output,
    }
    for _, arg in ipairs(overrides) do
        args[#args + 1] = arg
    end
    for _, kind in ipairs(OUTPUT_TYPES) do
        args[#args + 1] = "--output"
        args[#args + 1] = kind .. ":" .. output
    end
    for _, arg in ipairs(UNUSED_WRITERS) do
        args[#args + 1] = arg
    end
    for _, arg in ipairs({ "--use-postprocessor", postprocessor, "--", url }) do
        args[#args + 1] = arg
    end
    mp.msg.info("Loading the comments")
    run_ytdl(started, ytdl_paths(), 1, args)
end)

-- The tracks get the same IDs on each load because the script always adds them at this point.
mp.add_hook("on_preloaded", 50, function(hook)
    if not job then
        return
    end
    if job.result then
        finish(job, true)
    else
        job.hook = hook
        hook:defer()
    end
end)

local function remove_leftover_files()
    finish_unused_job()
    leftover_files = remove_files(leftover_files)
end

mp.register_event("end-file", remove_leftover_files)
mp.register_event("shutdown", remove_leftover_files)
