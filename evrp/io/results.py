import csv
import json
from pathlib import Path
from statistics import mean, stdev

from evrp.simulation.engine import RunResult


def save_result(result: RunResult, directory: str | Path) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{result.instance}_{result.algorithm}_seed{result.seed}.json"
    path = directory / name
    path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return path


def summary_row(result: RunResult) -> dict:
    row = {"instance": result.instance, "algorithm": result.algorithm, "seed": result.seed,
           **result.metrics, "trace_valid": result.validation["valid"]}
    row["unserved"] = ";".join(map(str, row["unserved"]))
    return row


def write_summary(results: list[RunResult], directory: str | Path) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if not results:
        return
    rows = [summary_row(r) for r in results]
    with (directory / "comparison.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    groups = {}
    for result in results:
        groups.setdefault((result.instance, result.algorithm), []).append(result)
    aggregates = []
    for (instance, algorithm), group in groups.items():
        complete = [r for r in group if r.metrics["objective_valid"]]
        row = {"instance": instance, "algorithm": algorithm, "runs": len(group),
               "valid_complete_runs": len(complete), "complete_rate": len(complete) / len(group),
               "served_mean": mean(r.metrics["served"] for r in group)}
        for metric in ("T_total", "C_electricity", "D_battery_degradation", "F"):
            values = [r.metrics[metric] for r in complete]
            row[f"{metric}_mean_complete"] = mean(values) if values else ""
            row[f"{metric}_std_complete"] = stdev(values) if len(values) > 1 else (0.0 if values else "")
        row["runtime_mean_seconds"] = mean(r.metrics["runtime_seconds"] for r in group)
        aggregates.append(row)
    with (directory / "statistics.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(aggregates[0]))
        writer.writeheader()
        writer.writerows(aggregates)
