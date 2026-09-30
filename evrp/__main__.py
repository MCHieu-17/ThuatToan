from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from .core import (DATA_URL, DEFAULT_ARCHIVE, Instance, load_instance,
                   make_releases, mst_double_tree, solve_online)


BENCHMARKS = (
    "tc0c10s2cf1", "tc1c10s2cf2", "tc2c10s2cf0",
    "tc0c20s3cf2", "tc1c20s3cf1", "tc2c20s3cf0",
    "tc0c40s5cf0", "tc1c40s5cf1", "tc2c40s5cf2",
)


def exact_tsp(instance: Instance) -> float:
    """Held-Karp dynamic programming, intended only for the 10-customer examples."""
    customers = list(instance.customers)
    n = len(customers)
    if n > 15:
        raise ValueError("Exact demonstration is limited to 15 customers")
    dp = {(1 << i, i): instance.distance(0, customer)
          for i, customer in enumerate(customers)}
    for mask in range(1, 1 << n):
        for last in range(n):
            current = dp.get((mask, last))
            if current is None:
                continue
            for nxt in range(n):
                if mask & (1 << nxt):
                    continue
                key = (mask | (1 << nxt), nxt)
                dp[key] = min(dp.get(key, math.inf),
                              current + instance.distance(customers[last], customers[nxt]))
    return min(dp[((1 << n) - 1, i)] + instance.distance(customers[i], 0)
               for i in range(n))


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dynamic EVRP-NL benchmark in Python")
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE,
                        help=f"Official Montoya ZIP; download from {DATA_URL}")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run one reproducible online scenario")
    run.add_argument("--instance", default=BENCHMARKS[0])
    run.add_argument("--method", choices=("greedy", "ga", "ga_vns"), default="ga_vns")
    run.add_argument("--dynamic-ratio", type=float, default=0.5)
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--seconds", type=float, default=2.0,
                     help="Best-effort solver budget per reveal event")
    run.add_argument("--output", type=Path, default=Path("results/run.json"))

    experiment = commands.add_parser("experiment", help="Run all 9 benchmark cases")
    experiment.add_argument("--output-dir", type=Path, default=Path("results/experiment"))
    experiment.add_argument("--seconds", type=float, default=2.0)
    experiment.add_argument("--limit-instances", type=int, default=9,
                            help="Use 1 for a quick smoke experiment")
    experiment.add_argument("--seeds", type=int, default=5)

    proof = commands.add_parser("proof", help="Evaluate the special-case 2-approximation")
    proof.add_argument("--instance", default=BENCHMARKS[0])

    report = commands.add_parser("report", help="Summarize experiment CSV and create plots")
    report.add_argument("--input", type=Path, default=Path("results/experiment/summary.csv"))
    report.add_argument("--output-dir", type=Path, default=Path("results/experiment"))

    args = parser.parse_args()
    if args.command != "report" and not args.archive.exists():
        parser.error(f"Archive not found: {args.archive}. Download it from {DATA_URL}")

    if args.command == "run":
        instance = load_instance(args.instance, args.archive)
        releases = make_releases(instance, args.dynamic_ratio, args.seed)
        result = solve_online(instance, releases, args.method, args.seed, args.seconds)
        result["dynamic_ratio"] = args.dynamic_ratio
        result["releases"] = {str(k): v for k, v in releases.items()}
        write_json(args.output, result)
        print(json.dumps({k: v for k, v in result.items() if k not in {"routes", "replans", "releases"}},
                         ensure_ascii=False, indent=2))
        print(f"Full trace: {args.output}")
    elif args.command == "experiment":
        if args.limit_instances < 1 or args.seeds < 1:
            parser.error("--limit-instances and --seeds must be positive")
        rows = []
        scenarios = {}
        for name in BENCHMARKS[:args.limit_instances]:
            instance = load_instance(name, args.archive)
            for ratio, seeds in ((0.0, (0,)), (0.5, range(args.seeds))):
                for seed in seeds:
                    releases = make_releases(instance, ratio, seed)
                    scenarios[f"{name}_{ratio}_{seed}"] = {str(k): v for k, v in releases.items()}
                    for method in ("greedy", "ga", "ga_vns"):
                        result = solve_online(instance, releases, method, seed, args.seconds)
                        latencies = [r["solve_seconds"] for r in result["replans"]]
                        ordered = sorted(latencies)
                        p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
                        row = {k: result[k] for k in ("instance", "method", "seed", "customers",
                                                      "served", "vehicles", "operating_hours",
                                                      "electricity_cost", "wear_proxy_kwh")}
                        row.update(dynamic_ratio=ratio, budget_seconds=args.seconds,
                                   unserved=len(result["unserved"]),
                                   replan_count=len(latencies),
                                   median_replan_seconds=ordered[len(ordered) // 2],
                                   p95_replan_seconds=p95,
                                   total_solve_seconds=sum(latencies),
                                   evaluations=sum(r["evaluations"] for r in result["replans"]))
                        rows.append(row)
                        print(name, ratio, seed, method, f"served={row['served']}",
                              f"CPU={row['total_solve_seconds']:.2f}s", flush=True)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        with (args.output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        write_json(args.output_dir / "scenarios.json", scenarios)
        print(f"Results: {args.output_dir / 'summary.csv'}")
    elif args.command == "proof":
        instance = load_instance(args.instance, args.archive)
        tour, length, mst = mst_double_tree(instance, instance.customers)
        result = {"instance": instance.name, "tour": tour, "tour_km": length,
                  "mst_km": mst, "ratio_to_mst": length / mst}
        if len(instance.customers) <= 15:
            optimal = exact_tsp(instance)
            result.update(optimal_km=optimal, ratio_to_optimal=length / optimal)
        print(json.dumps(result, indent=2))
    else:
        from .report import summarize

        print(f"Report: {summarize(args.input, args.output_dir)}")


if __name__ == "__main__":
    main()
