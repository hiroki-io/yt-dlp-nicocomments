#!/bin/sh
set -eu

if [ $# -eq 0 ]; then
    echo "usage: $0 [mpv options] file|URL..." >&2
    exit 2
fi

script=$0
while [ -L "$script" ]; do
    target=$(readlink -- "$script")
    case $target in
        /*) script=$target ;;
        *) script=$(dirname -- "$script")/$target ;;
    esac
done

directory=$(CDPATH= cd -- "$(dirname -- "$script")" && pwd)
exec mpv --script="$directory/nicocomments-display-fps.lua" --script="$directory/nicocomments-url.lua" \
    --video-sync=display-resample "$@"
