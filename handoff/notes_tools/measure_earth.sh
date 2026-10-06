#!/bin/bash
# Earth's rivers on the code of the snapshot (the working tree as it stood when the snapshot was made): provisional numbers,
# to be run again on the committed code and compared line for line.
F=/tmp/claude-0/-home-claude/059ceeac-064c-547a-88dd-cb05ea65ee21/scratchpad/step2/fifth
cd $F/snapshot
export PYTHONPATH=$F/snapshot/src
export WORLDENGINE_REFERENCE_DATA=/home/claude/world-engine/reference_data
L=$F/logs
T=$F/snapshot/timed.py
cat > $T <<'PY'
import resource, subprocess, sys, time
t = time.time()
code = subprocess.call(sys.argv[2:], stdout=open(sys.argv[1], "w"), stderr=subprocess.STDOUT)
peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1e6
open(sys.argv[1] + ".time", "w").write(f"{time.time() - t:.1f} s; peak memory {peak:.2f} GB; exit {code}\n")
PY
run() { out=$1; shift; python $T $L/$out "$@"; echo "$(date +%H:%M:%S) $out $(cat $L/$out.time)" >> $L/progress.txt; }
run relief.log python tools/earth_relief.py
run rivers.log python tools/earth_rivers.py
run demand.log python tools/earth_demand.py
run rivers_s20.log python tools/earth_rivers.py --settlements 20
run planet.log python tools/earth_rivers.py --sea-water planet
run planet_s20.log python tools/earth_rivers.py --sea-water planet --settlements 20
run planet_relief.log python tools/earth_relief.py --sea-water planet
run rivers_d076.log python tools/earth_rivers.py --demand-times 0.76
for s in 0.02 0.05 0.2 0.3 0.5 0.07 0.08 0.09 0.11 0.12 0.13 0.15; do run shares/share_$s.log python tools/earth_rivers.py --valley-share $s --settlements 20; done
for r in Amazon Nile Mississippi Congo Yangtze Ob Mackenzie Danube Ganges Parana Niger Lena Yenisei Indus Murray Volga Zambezi Orinoco "St Lawrence" Columbia Rhine Mekong Amur "Huang He"; do run "traces/trace_${r// /_}.log" python tools/earth_rivers.py --trace "$r"; done
run rivers_s100.log python tools/earth_rivers.py --settlements 100 --demands
echo "$(date +%H:%M:%S) all done" >> $L/progress.txt
