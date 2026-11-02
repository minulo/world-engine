#!/bin/sh
# Open the World Engine control panel (macOS; it works on Linux too): a window that shows whether the world engine
# runs, with buttons to start, stop, open, upgrade and delete it. Double-click this file in the Finder (it opens a
# Terminal window, which may be closed once the panel is open), or run it in Terminal:
#
#   scripts/panel.command                   open the panel
#   scripts/panel.command --install-app     make ~/Applications/World Engine.app; open the panel from there from now on
#   scripts/panel.command --self-test       open the panel, show every state, close (for CI)
#
# The panel needs a Python with tkinter: Python 3.13 from python.org has it; Homebrew's needs brew install python-tk@3.13.
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
PANEL=$ROOT/panel/world_engine_panel.py
PYTHON=''
if [ "${1:-}" = --python ]; then PYTHON=${2:?--python needs a path}; shift 2; fi
version_of() { "$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null; }

NOTK='' NOTK_V=''
if [ -z "$PYTHON" ]; then
    for v in 3.13 3.12 3.14; do
        for exe in "python$v" "/opt/homebrew/bin/python$v" "/usr/local/bin/python$v" \
                   "/Library/Frameworks/Python.framework/Versions/$v/bin/python3" python3; do
            path=$(command -v "$exe" 2>/dev/null) || continue
            [ "$path" = /usr/bin/python3 ] && [ "$(uname -s)" = Darwin ] && continue  # Apple's 3.9, which may ask to install tools
            [ "$(version_of "$path")" = "$v" ] || continue
            if "$path" -c 'import tkinter' >/dev/null 2>&1; then PYTHON=$path; break 2; fi
            [ -n "$NOTK" ] || { NOTK=$path NOTK_V=$v; }
        done
    done
elif ! "$PYTHON" -c 'import tkinter' >/dev/null 2>&1; then
    NOTK=$PYTHON NOTK_V=$(version_of "$PYTHON" || echo 3.13) PYTHON=''
fi
if [ -z "$PYTHON" ]; then
    if [ -n "$NOTK" ]; then
        cat >&2 <<EOF
The Python $NOTK has no tkinter, which the panel needs. Either:
  brew install python-tk@$NOTK_V                     (for Homebrew's Python)
  or install Python $NOTK_V from https://www.python.org/downloads/ , which includes tkinter
  (on Ubuntu: sudo apt install python3-tk)
then run this again.
EOF
    else
        cat >&2 <<'EOF'
No Python 3.13 (nor 3.12 or 3.14) was found. Install Python 3.13 from https://www.python.org/downloads/ , or with
Homebrew: brew install python@3.13 python-tk@3.13. Then run this again, or name one:
  scripts/panel.command --python /path/to/python3.13
EOF
    fi
    exit 3
fi

if [ $# -gt 0 ]; then
    exec "$PYTHON" "$PANEL" "$@"
fi
# The window on its own, so that this Terminal window may be closed; what it prints goes to .worldengine/panel.log.
mkdir -p "$ROOT/.worldengine"
nohup "$PYTHON" "$PANEL" > "$ROOT/.worldengine/panel.log" 2>&1 &
echo "The World Engine panel is opening ($PYTHON). You may close this window."
echo "To open the panel like any app from now on: scripts/panel.command --install-app"
