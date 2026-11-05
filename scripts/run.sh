#!/bin/sh
# Install the world engine, build the default world once, and open it in the browser (macOS and Linux).
#
#   scripts/run.sh                         the first run installs and builds: a few minutes
#   scripts/run.sh --port 9000 --world worlds/other.zarr --profile preview --seed 7
#   scripts/run.sh --no-browser            serve without opening a browser
#   scripts/run.sh --check                 install, build, serve, fetch the page and /api/world, stop (for CI)
#
# Each step is skipped when it is done already: the environment .venv, the packages of requirements.lock (installed
# again only when the lock changes) and the world (built only if its folder is missing). Ctrl+C stops the server.
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
PROFILE=preview WORLD='' SEED='' PORT=8765 HOST=127.0.0.1 PYTHON='' OPEN=--open CHECK=''
usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
          echo "Options: --world PATH --profile NAME --seed N --port N --host ADDRESS --python EXE --no-browser --check"; }
while [ $# -gt 0 ]; do
    case "$1" in
        --world|--profile|--seed|--port|--host|--python)
            [ $# -ge 2 ] || { echo "run.sh: $1 needs a value" >&2; exit 2; }
            case "$1" in --world) WORLD=$2 ;; --profile) PROFILE=$2 ;; --seed) SEED=$2 ;; --port) PORT=$2 ;;
                         --host) HOST=$2 ;; --python) PYTHON=$2 ;; esac
            shift 2 ;;
        --no-browser) OPEN=; shift ;;
        --check) CHECK=--check OPEN=; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "run.sh: unknown option $1" >&2; usage >&2; exit 2 ;;
    esac
done
case "$WORLD" in ""|/*) ;; *) WORLD=$PWD/$WORLD ;; esac      # a path given is taken from where the command was run
cd "$ROOT"
if [ -z "$WORLD" ]; then
    if [ "$PROFILE" = preview ] && [ -z "$SEED" ]; then WORLD=worlds/first.zarr; else WORLD=worlds/$PROFILE${SEED:+-seed$SEED}.zarr; fi
fi

say() { printf '\n== %s\n' "$*"; }
version_of() { "$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null; }

# 1. The environment .venv, made once, with Python 3.13, for which the lock was made; else 3.12 or 3.14, on which the
#    same pins install but were not tested.
VPY=.venv/bin/python
if [ -e .venv ] && ! "$VPY" -c 'import sys' >/dev/null 2>&1; then
    say "The environment .venv does not run; making it again"; rm -rf .venv
fi
if [ -e .venv ]; then
    if [ -n "$PYTHON" ] && [ "$(version_of "$PYTHON")" != "$(version_of "$VPY")" ]; then
        echo "note: .venv was made with Python $(version_of "$VPY"); --python counts only when .venv is made. Delete .venv to make it with $PYTHON."
    fi
else
    if [ -z "$PYTHON" ]; then
        for v in 3.13 3.12 3.14; do
            for exe in "python$v" python3 python "/opt/homebrew/bin/python$v" "/usr/local/bin/python$v" \
                       "/Library/Frameworks/Python.framework/Versions/$v/bin/python3"; do
                path=$(command -v "$exe" 2>/dev/null) || continue
                [ "$path" = /usr/bin/python3 ] && [ "$(uname -s)" = Darwin ] && continue  # Apple's 3.9, which may ask to install tools
                if [ "$(version_of "$path")" = "$v" ]; then PYTHON=$path; break 2; fi
            done
        done
    fi
    if [ -z "$PYTHON" ]; then
        cat >&2 <<'EOF'
No Python 3.13 (nor 3.12 or 3.14) was found. Install Python 3.13, then run this again:
  macOS:                       the installer from https://www.python.org/downloads/ , or: brew install python@3.13
  Ubuntu 25.04, 25.10:         sudo apt install python3.13 python3.13-venv
  Ubuntu 22.04, 24.04, 26.04:  sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt update
                               sudo apt install python3.13 python3.13-venv
Or name one: scripts/run.sh --python /path/to/python3.13
EOF
        exit 3
    fi
    PYV=$(version_of "$PYTHON") || { echo "run.sh: $PYTHON does not run" >&2; exit 3; }
    [ "$PYV" = 3.13 ] || echo "note: using Python $PYV. requirements.lock was made and tested with 3.13; its pins install on 3.12 and 3.14 too, but nothing was tested there and a world may differ in its last digits."
    # numba and llvmlite, pinned in the lock, publish no wheels for Intel Macs (none since numba 0.63, December 2025).
    if [ "$(uname -s)" = Darwin ] && [ "$("$PYTHON" -c 'import platform; print(platform.machine())')" = x86_64 ]; then
        if [ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" = 1 ]; then
            echo "$PYTHON runs as Intel code under Rosetta. Use an Apple-silicon Python (python.org's installer, or Homebrew in /opt/homebrew)." >&2
        else
            echo "This is an Intel Mac. numba 0.68.0 and llvmlite 0.50.0, pinned in requirements.lock, publish no wheels for it, so" >&2
            echo "the engine cannot be installed here from the lock. Run it in Docker instead: README, \"Run it in Docker\"." >&2
        fi
        exit 3
    fi
    say "Making the environment .venv with $PYTHON (Python $PYV)"
    "$PYTHON" -m venv .venv || { rm -rf .venv; echo "Could not make the environment. On Ubuntu: sudo apt install python$PYV-venv" >&2; exit 3; }
fi

# 2. The pinned packages.
STAMP=$("$VPY" -c 'import hashlib, sys; print(hashlib.sha256(b"".join(open(f, "rb").read().replace(b"\r\n", b"\n") for f in ("requirements.lock", "pyproject.toml"))).hexdigest(), sys.version.split()[0])')
if [ "$(cat .venv/worldengine-installed 2>/dev/null)" != "$STAMP" ]; then
    say "Installing the pinned packages of requirements.lock (90 to 120 MB to download the first time)"
    if ! { "$VPY" -m pip install --disable-pip-version-check --only-binary=:all: -r requirements.lock &&
           "$VPY" -m pip install --disable-pip-version-check --quiet --no-deps -e .; }; then
        echo "The packages did not install (above: why). The lock needs Python 3.12 to 3.14 on 64-bit Windows, Linux or an Apple-silicon Mac." >&2
        exit 4
    fi
    echo "$STAMP" > .venv/worldengine-installed
else
    echo "The environment .venv holds the pinned packages already."
fi

# 3. The world, once.
if [ -e "$WORLD" ]; then
    echo "The world $WORLD exists; it is served as it is."
else
    say "Building the $PROFILE world into $WORLD: one to two minutes for the preview, 40 to 80 for the standard one"
    "$VPY" -m worldengine build --profile "$PROFILE" ${SEED:+--seed "$SEED"} --out "$WORLD"
fi

# 4. Serve it.
say "Serving $WORLD"
exec "$VPY" -m worldengine serve "$WORLD" --port "$PORT" --host "$HOST" $OPEN $CHECK
