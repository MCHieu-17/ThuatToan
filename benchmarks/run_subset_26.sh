#!/usr/bin/env bash
# Benchmark bo con 26 instance dai dien (2 ban moi o: A x so khach x t/f).
#
# Moi job xargs la MOT to hop (instance, algorithm, seed) de tan dung het so nhan.
#
# Vi du:
#   bash benchmarks/run_subset_26.sh
#   CONFIG=configs/benchmark.json SEEDS="42 43" JOBS=12 bash benchmarks/run_subset_26.sh
#
# Ket qua: results/benchmark_subset26/{comparison.csv,statistics.csv,pareto.csv,*.json}
set -euo pipefail

__START=$(date +%s)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DATA="${DATA:-data/enhanced}"
OUT="${OUT:-results/benchmark_subset26}"
CONFIG="${CONFIG:-configs/benchmark.json}"
ALGORITHMS="${ALGORITHMS:-greedy ga ga_vns}"
SEEDS="${SEEDS:-42 43}"
JOBS="${JOBS:-$(nproc)}"
MODE="${MODE:-dynamic}"
SELECTION="${SELECTION:-pareto}"

INSTANCES=(
  # 10 khach: A=0,1,2 x s2/s3 (cf/ct)
  tc0c10s2cf1 tc0c10s3ct1
  tc1c10s2cf3 tc1c10s3cf4
  tc2c10s2ct0 tc2c10s3cf0
  # 20 khach
  tc0c20s3cf2 tc0c20s4ct2
  tc1c20s3ct1 tc1c20s3cf4
  tc2c20s3ct0 tc2c20s4cf0
  # 40 khach
  tc0c40s5cf0 tc0c40s8ct4
  tc1c40s5ct1 tc1c40s8cf1
  tc2c40s5cf2 tc2c40s8ct3
  # 80 khach
  tc0c80s8cf1 tc0c80s12ct0
  tc1c80s8ct2 tc1c80s12cf2
  tc2c80s8cf3 tc2c80s12ct3
  # scaling: 160 khach
  tc0c160s16ct4 tc1c160s24cf0
)

TOTAL=$((${#INSTANCES[@]} * $(echo $ALGORITHMS | wc -w) * $(echo $SEEDS | wc -w)))

echo "instance set : ${#INSTANCES[@]} (subset dai dien)"
echo "data         : $DATA"
echo "output       : $OUT"
echo "config       : $CONFIG"
echo "algorithms   : $ALGORITHMS"
echo "seeds        : $SEEDS"
echo "jobs         : $JOBS"
echo "total runs   : $TOTAL"

mkdir -p "$OUT"

# Sinh tat ca to hop (instance algorithm seed), chay song song JOBS tien trinh.
for instance in "${INSTANCES[@]}"; do
  for algorithm in $ALGORITHMS; do
    for seed in $SEEDS; do
      echo "$instance $algorithm $seed"
    done
  done
done | DATA="$DATA" CONFIG="$CONFIG" OUT="$OUT" MODE="$MODE" SELECTION="$SELECTION" \
  xargs -P "$JOBS" -n 3 bash -c '
    python3 -m evrp run \
      --data "$DATA" --instance "$1" \
      --config "$CONFIG" --mode "$MODE" --selection "$SELECTION" \
      --algorithm "$2" --seed "$3" --output "$OUT" >/dev/null
  ' _

python3 benchmarks/collect_results.py "$OUT"
echo "done -> $OUT"
echo "total time: $(( $(date +%s) - __START ))s"
