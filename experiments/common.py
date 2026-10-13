"""Shared helpers for the experiment scripts."""
from __future__ import annotations

import csv
from pathlib import Path

from evrp.config import Config
from evrp.io.enhance import apply_meta, discover_enhanced, load_enhanced
from evrp.simulation import SimulationResult, simulate


def load_instance(path: Path, config: Config):
    instance, meta = load_enhanced(path)
    apply_meta(config, meta)
    return instance


def pick_by_size(data_dir: str | Path, sizes: list[int]) -> dict[int, Path]:
    """Pick one representative instance per customer count.

    Prefer p-median station placements (name contains "ct") and more stations,
    which are more often serviceable than randomly placed stations.
    """
    candidates: dict[int, list[tuple]] = {}
    for path in discover_enhanced(data_dir):
        instance, _ = load_enhanced(path)
        count = len(instance.customers)
        if count in sizes:
            candidates.setdefault(count, []).append(
                (("ct" in path.stem), len(instance.stations), path.stem, path))
    chosen: dict[int, Path] = {}
    for count, options in candidates.items():
        options.sort(reverse=True)
        chosen[count] = options[0][3]
    return chosen


def run_once(path: Path, config: Config, algorithm: str, seed: int, mode: str) -> SimulationResult:
    instance = load_instance(path, config)
    return simulate(instance, config, algorithm, seed, mode)


def write_rows(path: str | Path, rows: list[dict], fields: list[str]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return out