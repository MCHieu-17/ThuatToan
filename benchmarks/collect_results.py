#!/usr/bin/env python3
"""Gom ket qua benchmark tu cac file JSON da chay thanh comparison/statistics/pareto.

Dung boi cac script benchmarks/run_*.sh sau khi xargs da chay song song
cac to hop (instance, algorithm, seed). Khong chay lai thuat toan.

    python3 benchmarks/collect_results.py <output_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evrp.io.results import write_comparison, write_pareto, write_statistics
from evrp.simulation import SimulationResult


def load_results(output_dir: Path) -> list[SimulationResult]:
    results: list[SimulationResult] = []
    for path in sorted(output_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        results.append(SimulationResult(
            name=data["name"],
            algorithm=data["algorithm"],
            seed=data["seed"],
            mode=data["mode"],
            served=data["served"],
            total_customers=data["total_customers"],
            complete=data["complete"],
            runtime_seconds=data["runtime_seconds"],
            replans=data["replans"],
            metrics=data["metrics"],
            counters=data["counters"],
            unserved=data["unserved"],
            actions=data["actions"],
            config=data["config"],
            pareto_front=data.get("pareto_front", []),
        ))
    return results


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: collect_results.py <output_dir>", file=sys.stderr)
        return 2
    output_dir = Path(argv[0])
    results = load_results(output_dir)
    if not results:
        print(f"no result JSON found in {output_dir}", file=sys.stderr)
        return 1
    write_comparison(results, output_dir)
    write_statistics(results, output_dir)
    write_pareto(results, output_dir)
    print(f"collected {len(results)} runs -> {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
