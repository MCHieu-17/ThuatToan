"""Scaling experiment: measure work and runtime as the instance grows."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path

from evrp.config import load_config
from experiments.common import pick_by_size, run_once, write_rows

FIELDS = ["customers", "instance", "algorithm", "seed", "mode", "served", "total", "complete",
          "F", "runtime_seconds", "dp_calls", "labels_expanded", "evaluations",
          "insertion_candidates", "replans"]


def run_complexity(data_dir: str, sizes, algorithms, seeds, mode: str, base_config, output: str,
                   greedy_budget: float = 300.0, meta_budget: float | None = None,
                   verbose: bool = True):
    chosen = pick_by_size(data_dir, sizes)
    rows = []
    results = []
    for size in sorted(chosen):
        for seed in seeds:
            for algorithm in algorithms:
                config = copy.deepcopy(base_config)
                if algorithm == "greedy":
                    config.solver_budget_seconds = greedy_budget
                elif meta_budget is not None:
                    config.solver_budget_seconds = meta_budget
                result = run_once(chosen[size], config, algorithm, seed, mode)
                results.append(result)
                rows.append({
                    "customers": size,
                    "instance": result.name,
                    "algorithm": algorithm,
                    "seed": seed,
                    "mode": mode,
                    "served": result.served,
                    "total": result.total_customers,
                    "complete": result.complete,
                    "F": round(result.metrics["F"], 4),
                    "runtime_seconds": round(result.runtime_seconds, 4),
                    "dp_calls": result.counters["dp_calls"],
                    "labels_expanded": result.counters["labels_expanded"],
                    "evaluations": result.counters["evaluations"],
                    "insertion_candidates": result.counters["insertion_candidates"],
                    "replans": result.replans,
                })
                if verbose:
                    print(f"n={size:4} {result.name:16} {algorithm:7} seed={seed} "
                          f"served={result.served}/{result.total_customers} "
                          f"F={result.metrics['F']:.3f} t={result.runtime_seconds:.3f}s "
                          f"dp={result.counters['dp_calls']} labels={result.counters['labels_expanded']}",
                          flush=True)
    write_rows(Path(output) / "complexity.csv", rows, FIELDS)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="EVRP scaling experiment")
    parser.add_argument("--data", default="data/enhanced")
    parser.add_argument("--sizes", type=int, nargs="+", default=[10, 20, 40, 80])
    parser.add_argument("--algorithms", nargs="+", default=["greedy", "ga", "ga_vns"])
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43])
    parser.add_argument("--mode", choices=["static", "dynamic"], default="static")
    parser.add_argument("--config", default="configs/quick.json")
    parser.add_argument("--output", default="results/complexity")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    run_complexity(args.data, args.sizes, args.algorithms, args.seeds, args.mode, config, args.output)


if __name__ == "__main__":
    main()