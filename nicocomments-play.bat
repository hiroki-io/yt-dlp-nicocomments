@echo off
if "%~1"=="" (
    echo usage: %~nx0 [mpv options] file... 1>&2
    exit /b 2
)
mpv --script="%~dp0nicocomments-display-fps.lua" --video-sync=display-resample %*
