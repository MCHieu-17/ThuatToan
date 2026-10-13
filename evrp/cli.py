"""Command line interface: list, prepare, run, benchmark, complexity."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from evrp.config import load_config
from evrp.io.enhance import (apply_meta, discover_enhanced, load_enhanced, prepare_dataset)
from evrp.io.montoya import discover_instances, load_original
from evrp.io.results import save_result, write_comparison, write_statistics
from evrp.simulation import simulate


def resolve_instance(value: str, directory: str | Path) -> Path:
    path = Path(value)
    if path.is_file():
        return path
    stem = Path(value).stem
    direct = Path(directory) / f"{stem}.json"
    if direct.is_file():
        return direct
    matches = [p for p in discover_instances(directory) if p.stem == stem]
    if len(matches) == 1:
        return matches[0]
    enhanced = [p for p in discover_enhanced(directory) if p.stem == stem]
    if len(enhanced) == 1:
        return enhanced[0]
    raise ValueError(f"expected one file for '{value}' in {directory}, found {len(matches) + len(enhanced)}")


def load_problem(path: Path, config):
    if path.suffix.lower() == ".json":
        instance, meta = load_enhanced(path)
        apply_meta(config, meta)
    else:
        instance = load_original(path)
    return instance


def _print_result(result) -> None:
    metrics = result.metrics
    print(f"{result.name} {result.algorithm} {result.mode} seed={result.seed}: "
          f"served={result.served}/{result.total_customers} complete={result.complete} "
          f"F={metrics['F']:.4f} T={metrics['T']:.3f} "
          f"elec={metrics['electricity']:.3f} deg={metrics['degradation']:.3f} "
          f"front={len(getattr(result, 'pareto_front', []) or [])} "
          f"runtime={result.runtime_seconds:.3f}s", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Realtime EVRP (Montoya) lab")
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="list instances")
    listing.add_argument("--data", default="data/montoya-et-al-2017")

    prep = sub.add_parser("prepare", help="build the enhanced dataset")
    prep.add_argument("--data", default="data/montoya-et-al-2017")
    prep.add_argument("--out", default="data/enhanced")
    prep.add_argument("--config", default="configs/default.json")
    prep.add_argument("--energy-unit", choices=["Wh", "kWh"], default="Wh")

    run = sub.add_parser("run", help="run one instance")
    run.add_argument("--data", default="data/enhanced")
    run.add_argument("--instance", required=True)
    run.add_argument("--config", default="configs/default.json")
    run.add_argument("--algorithm", choices=["greedy", "ga", "ga_vns"], default="ga_vns")
    run.add_argument("--mode", choices=["static", "dynamic"], default="dynamic")
    run.add_argument("--selection", choices=["scalar", "pareto"], default="pareto",
                     help="GA selection: NSGA-II Pareto or scalarised rank")
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--output", default="results/run")

    bench = sub.add_parser("benchmark", help="run multiple instances/seeds/algorithms")
    bench.add_argument("--data", default="data/enhanced")
    bench.add_argument("--instances", nargs="+")
    bench.add_argument("--max-customers", type=int, default=40)
    bench.add_argument("--limit", type=int, default=3)
    bench.add_argument("--config", default="configs/default.json")
    bench.add_argument("--algorithms", nargs="+", default=["greedy", "ga", "ga_vns"])
    bench.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44])
    bench.add_argument("--mode", choices=["static", "dynamic"], default="dynamic")
    bench.add_argument("--selection", choices=["scalar", "pareto"], default="pareto")
    bench.add_argument("--output", default="results/benchmark")

    cx = sub.add_parser("complexity", help="scaling measurements by instance size")
    cx.add_argument("--data", default="data/enhanced")
    cx.add_argument("--sizes", type=int, nargs="+", default=[10, 20, 40, 80])
    cx.add_argument("--config", default="configs/default.json")
    cx.add_argument("--algorithms", nargs="+", default=["greedy", "ga", "ga_vns"])
    cx.add_argument("--seeds", type=int, nargs="+", default=[42, 43])
    cx.add_argument("--mode", choices=["static", "dynamic"], default="static")
    cx.add_argument("--greedy-budget", type=float, default=120.0)
    cx.add_argument("--meta-budget", type=float, default=15.0)
    cx.add_argument("--output", default="results/complexity")

    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            _list(args.data)
            return
        if args.command == "prepare":
            config = load_config(args.config)
            written = prepare_dataset(args.data, args.out, config, args.energy_unit)
            print(f"wrote {len(written)} enhanced instances to {Path(args.out).resolve()}")
            return
        if args.command == "run":
            config = load_config(args.config)
            config.pareto_selection = args.selection == "pareto"
            path = resolve_instance(args.instance, args.data)
            instance = load_problem(path, config)
            result = simulate(instance, config, args.algorithm, args.seed, args.mode)
            save_result(result, args.output)
            _print_result(result)
            print(f"results saved to {Path(args.output).resolve()}")
            return
        if args.command == "benchmark":
            _run_benchmark(args)
            return
        if args.command == "complexity":
            from experiments.complexity import run_complexity
            config = load_config(args.config)
            results = run_complexity(args.data, args.sizes, args.algorithms, args.seeds,
                                     args.mode, config, args.output,
                                     greedy_budget=args.greedy_budget,
                                     meta_budget=args.meta_budget)
            write_comparison(results, args.output)
            write_statistics(results, args.output)
            for result in results:
                _print_result(result)
            print(f"complexity results saved to {Path(args.output).resolve()}")
            return
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))


def _list(directory: str) -> None:
    files = discover_instances(directory) + discover_enhanced(directory)
    if not files:
        print(f"no instances found in {directory}")
        return
    for path in files:
        if path.suffix.lower() == ".json":
            instance, _ = load_enhanced(path)
        else:
            instance = load_original(path)
        dynamic = sum(1 for node in instance.nodes.values()
                      if node.kind == "customer" and node.release_hours > 0)
        print(f"{instance.name:24} customers={len(instance.customers):3} "
              f"stations={len(instance.stations):2} vehicles={instance.vehicles:3} "
              f"dynamic={dynamic:3} source={path.name}")


def _run_benchmark(args) -> None:
    if args.instances:
        paths = [resolve_instance(name, args.data) for name in args.instances]
    else:
        selected = []
        for path in _all_paths(args.data):
            instance = _load_instance_any(path)
            if len(instance.customers) <= args.max_customers:
                selected.append(path)
        paths = selected[:args.limit]
    if not paths:
        raise ValueError("no matching instances")
    results = []
    for path in paths:
        for seed in args.seeds:
            for algorithm in args.algorithms:
                config = load_config(args.config)
                config.pareto_selection = args.selection == "pareto"
                instance = load_problem(path, config)
                result = simulate(instance, config, algorithm, seed, args.mode)
                results.append(result)
                save_result(result, args.output)
                _print_result(result)
    write_comparison(results, args.output)
    write_statistics(results, args.output)
    print(f"benchmark saved to {Path(args.output).resolve()}")


def _all_paths(directory: str) -> list[Path]:
    files = discover_enhanced(directory)
    return files if files else discover_instances(directory)


def _load_instance_any(path: Path):
    if path.suffix.lower() == ".json":
        return load_enhanced(path)[0]
    return load_original(path)


if __name__ == "__main__":
    main()