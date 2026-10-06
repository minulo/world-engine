#!/bin/bash
# the four worlds on the committed code: build, report, scan of the "why" answers
S=/tmp/claude-0/-home-claude-world-engine/40ddc0f6-9b30-5080-a9da-54072bce01e8/scratchpad
cd /home/claude/world-engine
export PYTHONPATH=/home/claude/world-engine/src
L=$S/final/worlds; W=$S/worlds
mkdir -p $L $W
git rev-parse HEAD > $L/code_state.txt; git status --short >> $L/code_state.txt
T=$S/timed.py
run() { out=$1; shift; python $T $L/$out "$@"; echo "$(date +%H:%M:%S) $out $(cat $L/$out.time)" >> $L/progress.txt; }
run build_preview.log python -m worldengine build --profile preview --out $W/first.zarr
run report_preview.log python tools/world_report.py $W/first.zarr
run twin_preview.log python tools/earth_twin.py --profile preview --out $W/twin_preview.zarr
run scan_preview.log python tools/why_scan.py $W/first.zarr
run scan_twin_preview.log python tools/why_scan.py $W/twin_preview.zarr
run build_standard.log python -m worldengine build --profile standard --out $W/big.zarr
run report_standard.log python tools/world_report.py $W/big.zarr
run scan_standard.log python tools/why_scan.py $W/big.zarr --every 23
run twin_standard.log python tools/earth_twin.py --profile standard --out $W/twin_standard.zarr
run scan_twin_standard.log python tools/why_scan.py $W/twin_standard.zarr --every 23
du -sm $W/*.zarr > $L/sizes.txt
echo "$(date +%H:%M:%S) all done" >> $L/progress.txt
