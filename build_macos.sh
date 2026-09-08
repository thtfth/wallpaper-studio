#!/bin/bash
# Build the macOS zip. Run this ON a Mac with Python 3 installed.
# The people who download the zip do NOT need Python -- it ends up inside the app.
set -e
cd "$(dirname "$0")"

python3 -m pip install --upgrade pyinstaller
pyinstaller wallpaper-studio.spec --noconfirm

# The zip is named for the CPU it was built on: a binary built on Apple Silicon
# will not run on an Intel Mac, or the other way round.
arch_label="$(uname -m)"
case "$arch_label" in
    arm64) arch_label="AppleSilicon" ;;
    x86_64) arch_label="Intel" ;;
esac

rm -rf stage
mkdir -p "stage/Wallpaper Studio"
cp "dist/Wallpaper Studio" "stage/Wallpaper Studio/"
chmod +x "stage/Wallpaper Studio/Wallpaper Studio"
cp packaging/README-macOS.txt "stage/Wallpaper Studio/README.txt"

# ditto, not zip: it preserves the executable bit, without which the app
# won't launch on double-click after being unzipped.
out="WallpaperStudio-macOS-${arch_label}.zip"
rm -f "$out"
ditto -c -k --sequesterRsrc --keepParent "stage/Wallpaper Studio" "$out"

echo
echo "Done: $out"
