#!/bin/bash
# Wallpaper Studio launcher for macOS and Linux.
# If macOS opens this in TextEdit instead of running it, run once in Terminal:
#     chmod +x "/path/to/start.command"
cd "$(dirname "$0")" || exit 1
printf '\033]0;Wallpaper Studio\007'

# If this was started with `bash start.command`, make it double-clickable next time.
[ -x "$0" ] || chmod +x "$0" 2>/dev/null

# On a stock Mac /usr/bin/python3 is a stub: it exists, but running it only pops
# Apple's "install the developer tools" dialog. Skip it when the tools are absent.
SKIP_STUB=""
if [ "$(uname -s)" = "Darwin" ] && ! xcode-select -p >/dev/null 2>&1; then
    SKIP_STUB="/usr/bin/python3"
fi

PY=""
for c in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    found="$(command -v "$c" 2>/dev/null)" || continue
    [ -n "$found" ] || continue
    [ -n "$SKIP_STUB" ] && [ "$found" = "$SKIP_STUB" ] && continue
    # Confirm it actually runs and is Python 3, rather than trusting the name.
    "$found" -c 'import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1 || continue
    PY="$found"
    break
done

if [ -n "$PY" ]; then
    exec "$PY" wallpaper_server.py
fi

echo "Wallpaper Studio needs Python 3, and it isn't installed here."
echo
if [ "$(uname -s)" = "Darwin" ]; then
    echo "Two ways to get it:"
    echo "  1. Apple's command line developer tools - no account, no browser"
    echo "  2. The installer from python.org"
    echo
    read -r -p "Start option 1 now? [y/N] " answer
    case "$answer" in
        [Yy]*) xcode-select --install ;;
        *)     open "https://www.python.org/downloads/macos/" 2>/dev/null ;;
    esac
    echo
    echo "Once it finishes, double-click start.command again."
else
    echo "Install it with your package manager, then run this again:"
    echo "  sudo apt install python3      # Debian, Ubuntu, Mint"
    echo "  sudo dnf install python3      # Fedora"
    echo "  sudo pacman -S python         # Arch"
fi
echo
read -n 1 -s -r -p "Press any key to close."
echo
