#!/bin/sh
set -eu

if [ $# -eq 0 ]; then
    echo "usage: $0 [mpv options] file..." >&2
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

exec mpv --script="$(CDPATH= cd -- "$(dirname -- "$script")" && pwd)/nicocomments-display-fps.lua" \
    --video-sync=display-resample "$@"
