#!/usr/bin/env bash
# Sequential driver for the full sweep programme.
#
# Every stage is resumable: re-running this script skips cells already done and
# round-trip verified, so a kill at any point costs at most the cell in flight.
#
# STAGE ORDER IS BY VALUE, NOT BY TIER.
#
#   1. The ratio grid at all four tiers, because the ratio-vs-corpus-size curve is
#      the central deliverable and says nothing until every tier exists. [DONE]
#   2. A threads-only OFAT at 1GB and 4GB. the design spec question 4 asks where the
#      xz -T block-size floor actually kicks in, and the 64MB/256MB data already
#      answers the below-floor half (payloads of 16-67MB against a 128MiB floor
#      gave 0.99x-1.22x speedup). The missing half needs a payload ABOVE the floor,
#      which only the large tiers provide -- and that needs the threads axis only,
#      not the whole 100-cell performance block.
#   3. The remaining performance axes at 256MB, which refine questions already
#      answered at 64MB and so cost the least if cut short.

set -u
cd "$(dirname "$0")"
PY=./venv/Scripts/python.exe
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

stage() {
  echo ""
  echo "################################################################"
  echo "# $*"
  echo "# $(date '+%Y-%m-%d %H:%M:%S')"
  echo "################################################################"
}

ratio_grid() { "$PY" -u matrix.py sweep --corpus "$1" --profile full \
                 --results "$2" --resume --yes --no-ofat; }

threads_only() { "$PY" -u matrix.py sweep --corpus "$1" --profile full \
                   --results "$2" --resume --yes --threads 1,4,20 \
                   --ofat-axes threads; }

full_ofat() { "$PY" -u matrix.py sweep --corpus "$1" --profile full \
                --results "$2" --resume --yes --threads 1,4,20; }

# ---- priority 1: the curve (all four tiers) --------------------------------
stage "64MB / full matrix"
"$PY" -u matrix.py sweep --corpus ./corpus/pg19_64mb.txt --profile full \
  --results ./results/sweep_64mb.jsonl --resume --yes

stage "256MB / ratio grid";  ratio_grid ./corpus/pg19_256mb.txt ./results/sweep_256mb.jsonl
stage "1GB / ratio grid";    ratio_grid ./corpus/pg19_1gb.txt   ./results/sweep_1gb.jsonl
stage "4GB / ratio grid";    ratio_grid ./corpus/pg19_4gb.txt   ./results/sweep_4gb.jsonl

stage "analysis (all four tiers -- THE CURVE)"
"$PY" -u analyze.py --results ./results/ --out ./report/

# ---- priority 2: the above-floor half of the xz -T curve -------------------
stage "1GB / threads-only OFAT"
threads_only ./corpus/pg19_1gb.txt ./results/sweep_1gb.jsonl

stage "analysis"
"$PY" -u analyze.py --results ./results/ --out ./report/

stage "4GB / threads-only OFAT"
threads_only ./corpus/pg19_4gb.txt ./results/sweep_4gb.jsonl

stage "analysis"
"$PY" -u analyze.py --results ./results/ --out ./report/

# ---- priority 3: remaining performance axes at a second tier ---------------
stage "256MB / full performance OFAT"
full_ofat ./corpus/pg19_256mb.txt ./results/sweep_256mb.jsonl

stage "final analysis"
"$PY" -u analyze.py --results ./results/ --out ./report/

stage "ALL STAGES COMPLETE"
