#!/usr/bin/env bash
# Benchmark theo kich thuoc: 10, 20, 40, 80, 160, 320 khach hang.
# Moi kich thuoc chon vai instance dai dien (cung A, ty le khach/tram tuong tu).
#
# Vi du:
#   bash benchmarks/run_by_size.sh
#   CONFIG=configs/benchmark.json SEEDS="42 43" JOBS=12 bash benchmarks/run_by_size.sh
#
# Ket qua: results/benchmark_by_size/{comparison.csv,statistics.csv,pareto.csv,*.json}
set -euo pipefail

__START=$(date +%s)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DATA="${DATA:-data/enhanced}"
OUT="${OUT:-results/benchmark_by_size}"
CONFIG="${CONFIG:-configs/benchmark.json}"
ALGORITHMS="${ALGORITHMS:-greedy ga ga_vns}"
SEEDS="${SEEDS:-42 43}"
JOBS="${JOBS:-$(nproc)}"
MODE="${MODE:-dynamic}"
SELECTION="${SELECTION:-pareto}"

# Voi moi kich thuoc: 1 instance A=0 (rai deu) + 1 instance A=1/2 (cum/hon hop).
# Chon ten co trong dataset Montoya 2016.
INSTANCES=(
  # 10 khach
  tc0c10s2cf1 tc1c10s2cf3
  # 20 khach
  tc0c20s3cf2 tc1c20s3ct1
  # 40 khach
  tc0c40s5cf0 tc1c40s5ct1
  # 80 khach
  tc0c80s8cf1 tc1c80s8ct2
  # 160 khach
  tc0c160s16ct2 tc2c160s16ct1
  # 320 khach
  tc1c320s24ct2 tc2c320s24ct0
)

TOTAL=$((${#INSTANCES[@]} * $(echo $ALGORITHMS | wc -w) * $(echo $SEEDS | wc -w)))

echo "instance set : kich thuoc 10/20/40/80/160/320 x 2 ban"
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
