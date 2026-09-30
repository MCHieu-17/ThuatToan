"""Read-only benchmark endpoints and local, in-memory simulation jobs."""
from __future__ import annotations

import csv
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from evrp.__main__ import BENCHMARKS, exact_tsp
from evrp.core import DEFAULT_ARCHIVE, load_instance, make_releases, mst_double_tree, solve_online


ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / "results/experiment/summary.csv"
app = FastAPI(title="EVRP Visual Lab", version="1.0.0")
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="evrp-web")
jobs: dict[str, dict] = {}
job_lock = threading.Lock()


class RunRequest(BaseModel):
    instance: str = BENCHMARKS[0]
    dynamic_ratio: Literal[0.0, 0.5, 1.0] = 0.5
    seed: int = Field(default=0, ge=0, le=9999)
    seconds: Literal[0.1, 0.5, 2.0] = 0.1
    methods: list[Literal["greedy", "ga", "ga_vns"]] = Field(default_factory=lambda: ["ga_vns"], min_length=1, max_length=3)

    @field_validator("methods")
    @classmethod
    def unique_methods(cls, methods: list[str]) -> list[str]:
        if len(set(methods)) != len(methods):
            raise ValueError("Each method may be selected only once")
        return methods


def require_instance(name: str):
    if name not in BENCHMARKS:
        raise HTTPException(status_code=404, detail="Unknown benchmark instance")
    if not DEFAULT_ARCHIVE.exists():
        raise HTTPException(status_code=503, detail="Benchmark ZIP is missing from data/raw")
    return load_instance(name)


@app.get("/api/health")
def health():
    return {"ok": True, "archive_available": DEFAULT_ARCHIVE.exists(), "summary_available": SUMMARY.exists()}


@app.get("/api/instances")
def list_instances():
    return [{"name": name, "customers": len(instance.customers), "stations": len(instance.stations)}
            for name in BENCHMARKS for instance in (require_instance(name),)]


@app.get("/api/instances/{name}")
def get_instance(name: str):
    instance = require_instance(name)
    return {
        "name": instance.name,
        "nodes": [{"id": node.id, "kind": node.kind, "x": node.x, "y": node.y,
                   "station_type": node.station_type, "service_time": node.service_time}
                  for node in instance.nodes.values()],
        "customers": list(instance.customers), "stations": list(instance.stations),
        "speed_kmh": instance.speed_kmh,
        "consumption_wh_km": instance.consumption_wh_km,
        "battery_wh": instance.battery_wh,
        "max_route_hours": instance.max_route_hours,
        "curves": {kind: [{"energy_wh": energy, "hours": hours} for energy, hours in points]
                   for kind, points in instance.curves.items()},
        "tariff": [{"start": 0, "end": 2, "price": 1},
                   {"start": 2, "end": 5, "price": 3},
                   {"start": 5, "end": 24, "price": 1.5}],
    }


def execute_job(job_id: str, config: RunRequest) -> None:
    try:
        instance = load_instance(config.instance)
        releases = make_releases(instance, config.dynamic_ratio, config.seed)
        results = {}
        total_replans = len(set(releases.values()))
        for method_index, method in enumerate(config.methods):
            def report(done: int, total: int) -> None:
                with job_lock:
                    jobs[job_id]["progress"] = {
                        "method": method, "completed": done, "total": total,
                        "method_index": method_index + 1, "method_count": len(config.methods),
                    }

            result = solve_online(instance, releases, method, config.seed,
                                  config.seconds, include_trace=True, on_progress=report)
            result["releases"] = {str(key): value for key, value in releases.items()}
            result["dynamic_ratio"] = config.dynamic_ratio
            results[method] = result
            with job_lock:
                jobs[job_id]["results"] = dict(results)
        with job_lock:
            jobs[job_id]["status"] = "complete"
            jobs[job_id]["progress"] = {"method": config.methods[-1], "completed": total_replans,
                                        "total": total_replans, "method_index": len(config.methods),
                                        "method_count": len(config.methods)}
    except Exception as exc:
        with job_lock:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(exc)


@app.post("/api/runs", status_code=202)
def create_run(config: RunRequest):
    require_instance(config.instance)
    with job_lock:
        if any(job["status"] == "running" for job in jobs.values()):
            raise HTTPException(status_code=409, detail="A simulation is already running")
        # Keep a small recent history for this single-user local demo.
        for old_id in list(jobs)[:-19]:
            if jobs[old_id]["status"] != "running":
                del jobs[old_id]
        job_id = uuid4().hex
        jobs[job_id] = {"id": job_id, "status": "running", "progress": None,
                        "config": config.model_dump(), "results": {}, "error": None}
    executor.submit(execute_job, job_id, config)
    return {"id": job_id, "status": "running"}


@app.get("/api/runs/{job_id}")
def get_run(job_id: str):
    with job_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Run not found (jobs reset when backend restarts)")
        return dict(job)


@app.get("/api/experiments")
def experiments(instance: str | None = None, dynamic_ratio: float | None = None):
    if instance is not None and instance not in BENCHMARKS:
        raise HTTPException(status_code=404, detail="Unknown benchmark instance")
    if dynamic_ratio is not None and dynamic_ratio not in (0.0, 0.5):
        raise HTTPException(status_code=422, detail="Available experiment ratios are 0 and 0.5")
    if not SUMMARY.exists():
        raise HTTPException(status_code=503, detail="Experiment summary is missing")
    with SUMMARY.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows = [row for row in rows if (instance is None or row["instance"] == instance)
            and (dynamic_ratio is None or float(row["dynamic_ratio"]) == dynamic_ratio)]
    numeric = {"seed", "customers", "served", "vehicles", "unserved", "replan_count", "evaluations"}
    return [{key: (int(value) if key in numeric else float(value) if key not in {"instance", "method"}
                   else value) for key, value in row.items()} for row in rows]


@app.get("/api/proof/{name}")
def proof(name: str):
    instance = require_instance(name)
    tour, length, mst = mst_double_tree(instance, instance.customers)
    vertices = [0, *instance.customers]
    visited = {0}
    mst_edges = []
    while len(visited) < len(vertices):
        a, b = min(((a, b) for a in visited for b in vertices if b not in visited),
                   key=lambda pair: instance.distance(*pair))
        visited.add(b)
        mst_edges.append([a, b])
    optimum = exact_tsp(instance) if len(instance.customers) <= 15 else None
    return {"instance": name, "tour": tour, "mst_edges": mst_edges, "tour_km": length,
            "mst_km": mst, "upper_bound_km": 2 * mst,
            "optimal_km": optimum,
            "ratio_to_optimal": length / optimum if optimum and math.isfinite(optimum) else None,
            "scope": "Static one-vehicle metric TSP with no charging constraint"}
