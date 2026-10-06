#!/bin/bash
# the whole suite on the committed code, with the Earth data and without
cd /home/claude/world-engine
L=$1; mkdir -p $L
git rev-parse HEAD > $L/suite_code_state.txt; git status --short >> $L/suite_code_state.txt
date -u +"start %FT%TZ" > $L/suite_with_data.log
PYTHONPATH=src python -m pytest tests -p no:cacheprovider -rxXfE >> $L/suite_with_data.log 2>&1
date -u +"end %FT%TZ" >> $L/suite_with_data.log
date -u +"start %FT%TZ" > $L/suite_without_data.log
WORLDENGINE_REFERENCE_DATA=$L/no_such_folder PYTHONPATH=src python -m pytest tests -p no:cacheprovider -rxXfE >> $L/suite_without_data.log 2>&1
date -u +"end %FT%TZ" >> $L/suite_without_data.log
echo done > $L/suite.done
