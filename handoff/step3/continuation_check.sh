set -e
cd /home/user/world-engine
D=/tmp/claude-0/cont; rm -rf $D; mkdir -p $D
python -m worldengine build --profile preview --history-my 20 --out $D/a20.zarr --quiet
python -m worldengine build --profile preview --history-my 40 --continue-from $D/a20.zarr --out $D/b40.zarr --quiet
python -m worldengine build --profile preview --history-my 40 --out $D/c40.zarr --quiet
python - <<'PY'
from worldengine.store import StoreView
b, c = StoreView("/tmp/claude-0/cont/b40.zarr"), StoreView("/tmp/claude-0/cont/c40.zarr")
fb, fc = b.attrs["fingerprints"], c.attrs["fingerprints"]
diff = sorted(k for k in fc if fb.get(k) != fc[k])
print("fields and table columns compared:", len(fc), "differing:", len(diff), diff[:10])
print("world fingerprints equal:", b.attrs["world_fingerprint"] == c.attrs["world_fingerprint"])
PY
