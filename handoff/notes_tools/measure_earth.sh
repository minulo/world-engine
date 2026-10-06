#!/bin/bash
# Earth's rivers on the committed code (handoff/notes_tools/measure_earth.sh, paths adapted): compared with handoff/logs afterwards
S=/tmp/claude-0/-home-claude-world-engine/40ddc0f6-9b30-5080-a9da-54072bce01e8/scratchpad
cd /home/claude/world-engine
export PYTHONPATH=/home/claude/world-engine/src
L=$S/final/earth
mkdir -p $L/shares $L/traces
git rev-parse HEAD > $L/code_state.txt; git status --short >> $L/code_state.txt
T=$S/timed.py
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
