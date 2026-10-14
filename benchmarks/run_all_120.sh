#!/usr/bin/env bash
# Benchmark toan bo 120 instance Montoya tren ca 3 thuat toan.
#
# Vi du:
#   bash benchmarks/run_all_120.sh
#   CONFIG=configs/comparison.json SEEDS="42 43" JOBS=12 bash benchmarks/run_all_120.sh
#
# Ket qua: results/benchmark_all120/{comparison.csv,statistics.csv,pareto.csv,*.json}
set -euo pipefail

__START=$(date +%s)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DATA="${DATA:-data/montoya-et-al-2017}"
OUT="${OUT:-results/benchmark_all120}"
CONFIG="${CONFIG:-configs/benchmark.json}"
ALGORITHMS="${ALGORITHMS:-greedy ga ga_vns}"
SEEDS="${SEEDS:-42 43 44}"
JOBS="${JOBS:-$(nproc)}"
MODE="${MODE:-dynamic}"
SELECTION="${SELECTION:-pareto}"

INSTANCES=()
for xml in "$DATA"/*.xml; do INSTANCES+=("$(basename "$xml" .xml)"); done
TOTAL=$((${#INSTANCES[@]} * $(echo $ALGORITHMS | wc -w) * $(echo $SEEDS | wc -w)))

echo "instance set : ${#INSTANCES[@]} (Montoya day du)"
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
