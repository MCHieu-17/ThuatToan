"""Persist simulation results as JSON plus comparison/statistics CSV files."""
from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

from evrp.simulation import SimulationResult

COMPARISON_COLUMNS = [
    "instance", "algorithm", "mode", "seed", "served", "total", "complete",
    "F", "T", "drive", "wait", "charge", "electricity", "degradation",
    "deep_charge", "deep_discharge", "makespan", "runtime_seconds", "replans",
    "dp_calls", "labels_expanded", "evaluations", "insertion_candidates",
]


def save_result(result: SimulationResult, output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{result.name}_{result.algorithm}_{result.mode}_seed{result.seed}.json"
    path.write_text(json.dumps(result.__dict__, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def _row(result: SimulationResult) -> dict:
    metrics = result.metrics
    counters = result.counters
    return {
        "instance": result.name,
        "algorithm": result.algorithm,
        "mode": result.mode,
        "seed": result.seed,
        "served": result.served,
        "total": result.total_customers,
        "complete": result.complete,
        "F": metrics["F"],
        "T": metrics["T"],
        "drive": metrics["drive"],
        "wait": metrics["wait"],
        "charge": metrics["charge"],
        "electricity": metrics["electricity"],
        "degradation": metrics["degradation"],
        "deep_charge": metrics["deep_charge"],
        "deep_discharge": metrics["deep_discharge"],
        "makespan": metrics["makespan"],
        "runtime_seconds": result.runtime_seconds,
        "replans": result.replans,
        "dp_calls": counters["dp_calls"],
        "labels_expanded": counters["labels_expanded"],
        "evaluations": counters["evaluations"],
        "insertion_candidates": counters["insertion_candidates"],
    }


def write_comparison(results: list[SimulationResult], output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "comparison.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMPARISON_COLUMNS)
        writer.writeheader()
        for result in results:
            writer.writerow(_row(result))
    return path


PARETO_COLUMNS = ["instance", "algorithm", "mode", "seed", "unassigned", "time",
                  "electricity", "degradation", "score", "complete"]


def write_pareto(results: list[SimulationResult], output_dir: str | Path) -> Path | None:
    """Write the union of per-run non-dominated fronts to pareto.csv (if any)."""
    rows = []
    for result in results:
        for point in getattr(result, "pareto_front", []) or []:
            rows.append({
                "instance": result.name,
                "algorithm": result.algorithm,
                "mode": result.mode,
                "seed": result.seed,
                "unassigned": point.get("unassigned"),
                "time": point.get("time"),
                "electricity": point.get("electricity"),
                "degradation": point.get("degradation"),
                "score": point.get("score"),
                "complete": point.get("complete"),
            })
    if not rows:
        return None
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "pareto.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PARETO_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_statistics(results: list[SimulationResult], output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    groups: dict[tuple[str, str, str], list[SimulationResult]] = {}
    for result in results:
        groups.setdefault((result.name, result.mode, result.algorithm), []).append(result)
    path = out / "statistics.csv"
    fields = ["instance", "mode", "algorithm", "runs", "complete_runs", "served_mean",
              "F_mean", "F_std", "runtime_mean", "dp_calls_mean", "labels_mean"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for (name, mode, algorithm), group in sorted(groups.items()):
            complete = [r for r in group if r.complete]
            scores = [r.metrics["F"] for r in complete]
            writer.writerow({
                "instance": name,
                "mode": mode,
                "algorithm": algorithm,
                "runs": len(group),
                "complete_runs": len(complete),
                "served_mean": round(statistics.mean(r.served for r in group), 3),
                "F_mean": round(statistics.mean(scores), 4) if scores else "",
                "F_std": round(statistics.pstdev(scores), 4) if len(scores) > 1 else (0.0 if scores else ""),
                "runtime_mean": round(statistics.mean(r.runtime_seconds for r in group), 4),
                "dp_calls_mean": round(statistics.mean(r.counters["dp_calls"] for r in group), 2),
                "labels_mean": round(statistics.mean(r.counters["labels_expanded"] for r in group), 2),
            })
    return path