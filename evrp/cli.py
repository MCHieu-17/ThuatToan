from __future__ import annotations

import argparse
import json
from pathlib import Path

from evrp.config import load_config
from evrp.io.montoya import discover_instances, load_instance
from evrp.io.results import save_result, write_summary
from evrp.scenario import generate_scenario
from evrp.simulation.engine import simulate


def resolve_instance(value: str, directory: str) -> Path:
    if Path(value).is_file():
        return Path(value)
    matches = [p for p in discover_instances(directory) if p.stem == Path(value).stem]
    if len(matches) != 1:
        raise ValueError(f"Expected one XML for '{value}', found {len(matches)} in {directory}")
    return matches[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Montoya EVRP: Greedy + DP versus GA + VNS + DP")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="Inspect XML instances without running a solver")
    listing.add_argument("--data", default="data/montoya-et-al-2017")
    listing.add_argument("--energy-unit", choices=["Wh", "kWh"], default="Wh")
    for name in ("run", "benchmark"):
        p = sub.add_parser(name)
        p.add_argument("--data", default="data/montoya-et-al-2017")
        p.add_argument("--config", default="configs/default.json")
        p.add_argument("--energy-unit", choices=["Wh", "kWh"], default="Wh")
        p.add_argument("--algorithm", choices=["baseline", "ga_vns", "both"], default="both")
        p.add_argument("--output", default=f"results/{name}")
        if name == "run":
            p.add_argument("--instance", help="Instance stem or XML path")
            p.add_argument("--demo", action="store_true", help="Use clearly labeled synthetic fixture")
            p.add_argument("--seed", type=int)
        else:
            p.add_argument("--instances", nargs="+", help="Instance stems/paths; otherwise filter the directory")
            p.add_argument("--max-customers", type=int, default=20)
            p.add_argument("--limit", type=int, default=3)
            p.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44])
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            files = discover_instances(args.data)
            if not files:
                raise ValueError(f"No XML found in {args.data}. Put the Montoya files there first.")
            for path in files:
                instance = load_instance(path, args.energy_unit)
                print(f"{instance.name:24} customers={len(instance.customers):3} "
                      f"stations={len(instance.stations):2} Q={instance.capacity_kwh:g} kWh "
                      f"horizon={instance.horizon_hours:g} h")
            return
        config = load_config(args.config)
        if args.command == "run":
            if args.demo and args.instance:
                raise ValueError("Use either --demo or --instance")
            if not args.demo and not args.instance:
                raise ValueError("Specify --instance tc0c10s2cf1 or --demo")
            paths = [Path("data/demo.xml") if args.demo else resolve_instance(args.instance, args.data)]
            seeds = [config.seed if args.seed is None else args.seed]
        else:
            if args.limit <= 0 or args.max_customers <= 0:
                raise ValueError("--limit and --max-customers must be positive")
            paths = [resolve_instance(n, args.data) for n in args.instances] if args.instances else [
                p for p in discover_instances(args.data)
                if len(load_instance(p, args.energy_unit).customers) <= args.max_customers][:args.limit]
            seeds = args.seeds
        if not paths:
            raise ValueError("No matching instances")
        algorithms = ["baseline", "ga_vns"] if args.algorithm == "both" else [args.algorithm]
        results = []
        for path in paths:
            instance = load_instance(path, "Wh" if args.command == "run" and args.demo else args.energy_unit)
            for seed in seeds:
                scenario = generate_scenario(instance, config, seed)
                for algorithm in algorithms:
                    result = simulate(instance, config, scenario, algorithm)
                    save_result(result, args.output)
                    results.append(result)
                    write_summary(results, args.output)
                    m = result.metrics
                    print(f"{instance.name} seed={seed} {algorithm}: served={m['served']}/{m['total_customers']} "
                          f"F={m['F']:.4f} valid_full={m['objective_valid']} "
                          f"runtime={m['runtime_seconds']:.2f}s", flush=True)
                    if not result.validation["valid"]:
                        raise RuntimeError(json.dumps(result.validation, ensure_ascii=False))
        print(f"Results saved to {Path(args.output).resolve()}")
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
