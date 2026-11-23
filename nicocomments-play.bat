@echo off
if "%~1"=="" (
    echo usage: %~nx0 [mpv options] file^|URL... 1>&2
    exit /b 2
)
mpv --script="%~dp0nicocomments-display-fps.lua" --script="%~dp0nicocomments-url.lua" --video-sync=display-resample %*
