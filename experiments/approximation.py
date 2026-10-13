"""Approximation-ratio verification on a simplified EVRP special case.

Theoretical analysis (see REPORT.md) proves the charging subproblem is solved
exactly by the DP and gives an end-to-end alpha for the simplified model:
linear charging, a single constant tariff band and unlimited station capacity,
with a single vehicle. This script builds that special case from the enhanced
dataset and compares the Greedy + DP baseline against an exhaustive reference
optimum obtained by enumerating every customer permutation.
"""
from __future__ import annotations

import argparse
import copy
import itertools
import math
from pathlib import Path

from evrp.algorithms.evaluator import FleetEvaluator
from evrp.algorithms.ga_vns import run_ga_vns, run_pure_ga
from evrp.algorithms.greedy import greedy_insert
from evrp.config import load_config
from evrp.domain import CUSTOMER, Curve, Instance, StationInfo, VehicleState
from evrp.io.enhance import apply_meta, load_enhanced
from experiments.common import write_rows

DEFAULT_INSTANCES = ["tc2c10s2ct0", "tc2c10s3ct0", "tc1c10s2ct2", "tc1c10s3ct2",
                     "tc1c10s2cf2", "tc1c10s3cf2"]
FIELDS = ["customers", "instance", "algorithm", "seed", "complete", "served", "total",
          "F", "opt", "ratio", "dp_calls"]


def linear_curve(capacity_kwh: float, power_kw: float) -> Curve:
    """Constant-power (linear) charging curve from empty to full."""
    return Curve(((0.0, 0.0), (capacity_kwh, capacity_kwh / power_kw)))


def simplify_instance(instance: Instance, customers: int) -> Instance:
    """Subsample customers plus linearize charging and free station capacity."""
    simplified = copy.deepcopy(instance)
    keep = {instance.depot} | set(instance.stations) | set(instance.customers[:customers])
    simplified.nodes = {node_id: node for node_id, node in instance.nodes.items() if node_id in keep}
    simplified.curves = {name: linear_curve(simplified.capacity_kwh, 40.0)
                         for name in instance.curves}
    simplified.stations_info = {
        station_id: StationInfo(ports=10_000, power_kw=1_000_000.0, charger_kw=1_000_000.0)
        for station_id in instance.stations_info
    }
    simplified.vehicles = 1
    return simplified


def load_simplified(path: Path, n: int, config) -> Instance:
    instance, meta = load_enhanced(path)
    apply_meta(config, meta)
    config.tou = [{"start": 0.0, "end": 24.0, "price": 0.12}]
    config.w_degradation = 0.0
    config.vehicles = 1
    config.validate()
    return simplify_instance(instance, n)


def _fresh_evaluator(instance: Instance, config):
    customers = instance.customers
    releases = {c: 0.0 for c in customers}
    states = {0: VehicleState(0, instance.depot, 0.0, instance.capacity_kwh)}
    evaluator = FleetEvaluator(instance, config, releases, states, customers)
    evaluator.deadline = None
    return evaluator


def reference_optimum(instance: Instance, config) -> float:
    """Exact optimum for one vehicle by enumerating every customer permutation."""
    customers = list(instance.customers)
    evaluator = _fresh_evaluator(instance, config)
    best = math.inf
    for permutation in itertools.permutations(customers):
        solution = evaluator.evaluate({0: list(permutation)})
        if solution.complete and solution.score < best:
            best = solution.score
    return best


def _solve_algorithm(instance: Instance, config, algorithm: str, seed: int):
    evaluator = _fresh_evaluator(instance, config)
    if algorithm == "greedy":
        return greedy_insert(evaluator)
    if algorithm == "ga":
        return run_pure_ga(evaluator, seed=seed)
    if algorithm == "ga_vns":
        return run_ga_vns(evaluator, seed=seed)
    raise ValueError(f"unknown algorithm {algorithm!r}")


def run_approximation(data_dir: str, instances, sizes, algorithms, seeds, base_config, output: str,
                      verbose: bool = True):
    data = Path(data_dir)
    rows = []
    for size in sorted(sizes):
        for name in instances:
            path = data / f"{name}.json"
            if not path.is_file():
                continue
            config = copy.deepcopy(base_config)
            instance = load_simplified(path, size, config)
            if len(instance.customers) < size:
                continue
            optimum = reference_optimum(instance, config)
            if not math.isfinite(optimum):
                if verbose:
                    print(f"n={size} {instance.name:16} skip (no feasible single-vehicle tour)",
                          flush=True)
                continue
            for seed in seeds:
                for algorithm in algorithms:
                    solution = _solve_algorithm(instance, config, algorithm, seed)
                    complete = solution.complete
                    ratio = (solution.score / optimum
                             if complete and math.isfinite(optimum) and optimum > 0 else None)
                    rows.append({
                        "customers": size,
                        "instance": instance.name,
                        "algorithm": algorithm,
                        "seed": seed,
                        "complete": complete,
                        "served": len(instance.customers) - len(solution.unassigned),
                        "total": len(instance.customers),
                        "F": round(solution.score, 6) if math.isfinite(solution.score) else "",
                        "opt": round(optimum, 6) if math.isfinite(optimum) else "",
                        "ratio": round(ratio, 4) if ratio is not None else "",
                        "dp_calls": solution.evaluations,
                    })
                    if verbose:
                        shown = f"{ratio:.4f}" if ratio is not None else "n/a"
                        print(f"n={size} {instance.name:16} {algorithm:7} seed={seed} "
                              f"complete={complete} F={solution.score:.3f} opt={optimum:.3f} "
                              f"ratio={shown}", flush=True)
    write_rows(Path(output) / "approximation.csv", rows, FIELDS)
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description="Approximation-ratio verification")
    parser.add_argument("--data", default="data/enhanced")
    parser.add_argument("--instances", nargs="+", default=DEFAULT_INSTANCES)
    parser.add_argument("--sizes", type=int, nargs="+", default=[4, 5, 6])
    parser.add_argument("--algorithms", nargs="+", default=["greedy", "ga", "ga_vns"])
    parser.add_argument("--seeds", type=int, nargs="+", default=[42])
    parser.add_argument("--config", default="configs/approximation.json")
    parser.add_argument("--output", default="results/approximation")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    run_approximation(args.data, args.instances, args.sizes, args.algorithms, args.seeds,
                      config, args.output)


if __name__ == "__main__":
    main()