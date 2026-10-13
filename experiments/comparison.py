"""Algorithm comparison experiment: greedy+DP vs pure GA vs hybrid GA-VNS."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path

from evrp.config import load_config
from evrp.io.results import write_comparison, write_pareto, write_statistics
from experiments.common import run_once, write_rows


DEFAULT_INSTANCES = [
    "tc0c10s2ct1", "tc0c10s3ct1", "tc1c10s2cf2", "tc1c10s2ct4", "tc1c10s3cf2",
]

FIELDS = ["instance", "algorithm", "seed", "mode", "served", "total", "complete",
          "F", "T", "electricity", "degradation", "deep_charge", "deep_discharge",
          "runtime_seconds", "dp_calls", "labels_expanded", "evaluations"]


def run_comparison(data_dir: str, instances, algorithms, seeds, mode: str, base_config,
                   output: str, verbose: bool = True):
    rows = []
    results = []
    for name in instances:
        path = Path(data_dir) / f"{name}.json"
        if not path.is_file():
            path = Path(name)
        for seed in seeds:
            for algorithm in algorithms:
                config = copy.deepcopy(base_config)
                result = run_once(path, config, algorithm, seed, mode)
                results.append(result)
                rows.append({
                    "instance": result.name,
                    "algorithm": algorithm,
                    "seed": seed,
                    "mode": mode,
                    "served": result.served,
                    "total": result.total_customers,
                    "complete": result.complete,
                    "F": round(result.metrics["F"], 4),
                    "T": round(result.metrics["T"], 4),
                    "electricity": round(result.metrics["electricity"], 4),
                    "degradation": round(result.metrics["degradation"], 4),
                    "deep_charge": result.metrics["deep_charge"],
                    "deep_discharge": result.metrics["deep_discharge"],
                    "runtime_seconds": round(result.runtime_seconds, 4),
                    "dp_calls": result.counters["dp_calls"],
                    "labels_expanded": result.counters["labels_expanded"],
                    "evaluations": result.counters["evaluations"],
                })
                if verbose:
                    print(f"{result.name:16} {algorithm:7} seed={seed} "
                          f"served={result.served}/{result.total_customers} "
                          f"complete={result.complete} F={result.metrics['F']:.3f} "
                          f"t={result.runtime_seconds:.3f}s", flush=True)
    write_rows(Path(output) / "comparison_rows.csv", rows, FIELDS)
    write_comparison(results, output)
    write_statistics(results, output)
    write_pareto(results, output)
    return results, rows


def improvement_summary(rows) -> list[dict]:
    """Pairwise F improvement of GA/GA-VNS over greedy on complete runs."""
    by_key = {(r["instance"], r["seed"], r["algorithm"]): r for r in rows}
    summary = []
    instances = sorted({r["instance"] for r in rows})
    for name in instances:
        seeds = sorted({r["seed"] for r in rows if r["instance"] == name})
        for seed in seeds:
            base = by_key.get((name, seed, "greedy"))
            if not base or not base["complete"]:
                continue
            for algorithm in ("ga", "ga_vns"):
                other = by_key.get((name, seed, algorithm))
                if not other or not other["complete"]:
                    continue
                summary.append({
                    "instance": name,
                    "seed": seed,
                    "algorithm": algorithm,
                    "greedy_F": base["F"],
                    "algorithm_F": other["F"],
                    "improvement_pct": round(100.0 * (base["F"] - other["F"]) / base["F"], 3),
                })
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="EVRP algorithm comparison")
    parser.add_argument("--data", default="data/enhanced")
    parser.add_argument("--instances", nargs="+", default=DEFAULT_INSTANCES)
    parser.add_argument("--algorithms", nargs="+", default=["greedy", "ga", "ga_vns"])
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44])
    parser.add_argument("--mode", choices=["static", "dynamic"], default="static")
    parser.add_argument("--config", default="configs/quick.json")
    parser.add_argument("--output", default="results/comparison")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    run_comparison(args.data, args.instances, args.algorithms, args.seeds, args.mode,
                   config, args.output)


if __name__ == "__main__":
    main()