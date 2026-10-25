#!/bin/sh
# What the container runs (Dockerfile): build the world into the volume /app/worlds if it is not there, then serve it on
# every address of the container, for the port that `docker run -p` publishes. Options are passed on to `serve`
# (for example --check). The world, the profile and the port can be set with WORLDENGINE_WORLD, WORLDENGINE_PROFILE
# and WORLDENGINE_PORT.
set -eu
PROFILE=${WORLDENGINE_PROFILE:-preview}
if [ "$PROFILE" = preview ]; then WORLD=${WORLDENGINE_WORLD:-/app/worlds/first.zarr}; else WORLD=${WORLDENGINE_WORLD:-/app/worlds/$PROFILE.zarr}; fi
PORT=${WORLDENGINE_PORT:-8765}
if [ -e "$WORLD" ]; then
    echo "The world $WORLD exists; it is served as it is."
else
    echo "Building the $PROFILE world into $WORLD: one to two minutes for the preview, 40 to 80 for the standard one."
    python -m worldengine build --profile "$PROFILE" --out "$WORLD"
fi
echo "On the machine that runs Docker, the viewer is at http://localhost:<the port published with -p>/ (8765 in the README)."
echo "The server listens on every address of the container; who reaches it is set by -p (127.0.0.1:8765:8765: this machine only)."
exec python -m worldengine serve "$WORLD" --host 0.0.0.0 --port "$PORT" "$@"
