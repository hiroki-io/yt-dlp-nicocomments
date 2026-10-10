#!/bin/sh
set -eu

usage() {
    echo "usage: $0 --major|--minor|--patch" >&2
    exit 2
}

[ $# -eq 1 ] || usage
case "$1" in
--major | --minor | --patch) part="${1#--}" ;;
*) usage ;;
esac

notes_dir="$(cd "$(dirname "$0")" && pwd)/release-notes"
latest="$(git -C "$notes_dir" tag -l --sort=-v:refname | grep -Ex '(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*)){2}' | head -n 1 || true)"
IFS=. read -r major minor patch <<END
${latest:-0.0.0}
END
case "$part" in
major) version="$((major + 1)).0.0" ;;
minor) version="$major.$((minor + 1)).0" ;;
patch) version="$major.$minor.$((patch + 1))" ;;
esac

if [ -n "$(git -C "$notes_dir" status --porcelain)" ]; then
    echo "the working tree is not clean" >&2
    exit 1
fi
if git -C "$notes_dir" rev-parse -q --verify "refs/tags/$version" > /dev/null; then
    echo "the tag $version already exists" >&2
    exit 1
fi
output="$notes_dir/$version.md"
if [ -e "$output" ]; then
    echo "$output already exists" >&2
    exit 1
fi
set -- "$notes_dir"/+*.md
if [ ! -e "$1" ]; then
    echo "no unreleased items in $notes_dir" >&2
    exit 1
fi
awk 1 "$@" > "$output"
rm -- "$@"
echo "$output"
git -C "$notes_dir" add -A -- .
git -C "$notes_dir" commit -q -m "Release $version"
git -C "$notes_dir" tag -s -m "$version" "$version"
