#!/usr/bin/env python3
"""Quet budget thoi gian de tim diem hoi tu chat luong.

Chay ga_vns/ga tren vai instance co vua voi nhieu budget + seed (static mode,
mot lan giai) va in bang F theo budget de chon solver_budget_seconds hop ly.

    python3 benchmarks/sweep_budget.py
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evrp.config import load_config
from evrp.io.montoya import load_original
from evrp.simulation import simulate

INSTANCES = ["tc0c20s3cf2", "tc0c40s5cf0", "tc0c80s8cf1"]
ALGORITHMS = ["ga", "ga_vns"]
SEEDS = [42, 43, 44]
BUDGETS = [1.0, 2.0, 4.0, 8.0, 16.0]
DATA = Path("data/montoya-et-al-2017")


def main():
    rows = []
    for name in INSTANCES:
        inst = load_original(DATA / f"{name}.xml")
        for algorithm in ALGORITHMS:
            for budget in BUDGETS:
                fs, serves, walls = [], [], []
                for seed in SEEDS:
                    config = load_config("configs/benchmark.json")
                    config.solver_budget_seconds = budget
                    t = time.perf_counter()
                    r = simulate(inst, config, algorithm, seed, "static")
                    walls.append(time.perf_counter() - t)
                    fs.append(r.metrics["F"])
                    serves.append(r.served / r.total_customers)
                rows.append({
                    "instance": name, "algorithm": algorithm, "budget": budget,
                    "F_mean": statistics.mean(fs),
                    "F_std": statistics.pstdev(fs) if len(fs) > 1 else 0.0,
                    "served_mean": statistics.mean(serves),
                    "wall_mean": statistics.mean(walls),
                })
                print(f"{name:14} {algorithm:7} budget={budget:5.1f}s "
                      f"F={rows[-1]['F_mean']:8.3f} +-{rows[-1]['F_std']:6.3f} "
                      f"served={rows[-1]['served_mean']:.2f} wall={rows[-1]['wall_mean']:.1f}s",
                      flush=True)

    print("\n=== F trung binh theo budget (gop moi instance/thuat toan) ===")
    for budget in BUDGETS:
        group = [r for r in rows if r["budget"] == budget]
        print(f"budget={budget:5.1f}s  F_gop={statistics.mean(r['F_mean'] for r in group):8.3f}  "
              f"served={statistics.mean(r['served_mean'] for r in group):.3f}  "
              f"wall={statistics.mean(r['wall_mean'] for r in group):5.1f}s")


if __name__ == "__main__":
    main()
