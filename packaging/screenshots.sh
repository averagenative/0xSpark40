#!/usr/bin/env bash
# Render the README screenshots in demo mode (no amp needed): the main window, the presets
# window, and every theme, plus a 480-pixel thumbnail of each. Settings go to a throwaway
# folder, so your own theme choice is left alone. Needs a graphical session and ImageMagick.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=docs/screenshots
mkdir -p "$OUT/thumbs"
export XDG_CONFIG_HOME="$(mktemp -d)"
trap 'rm -rf "$XDG_CONFIG_HOME"' EXIT

shot() {    # shot NAME THEME
    python3 -m spark40.gui --demo --theme "$2" --height 940 --screenshot "$OUT/$1.png" >/dev/null 2>&1
}
shot main black
for theme in black pearl spark2 vai live emerald purple blue adwaita neon metal; do
    shot "theme-$theme" "$theme"
done
python3 packaging/screenshot-presets.py "$OUT/presets.png" >/dev/null 2>&1

# Full size as lossless WebP (smallest for the textured themes), thumbnails as JPEG.
for png in "$OUT"/*.png; do
    name="$(basename "$png" .png)"
    magick "$png" -resize 480x -strip -quality 85 "$OUT/thumbs/$name.jpg"
    magick "$png" -strip -define webp:lossless=true "$OUT/$name.webp"
    rm "$png"
done
du -sh "$OUT"
