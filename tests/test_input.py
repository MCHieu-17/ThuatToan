from __future__ import annotations

from pathlib import Path

import pytest

from evrp.io.enhance import apply_meta, load_enhanced
from evrp.io.montoya import discover_instances, load_original

DATA = Path("data/montoya-et-al-2017")
ENHANCED = Path("data/enhanced")


def test_montoya_units_and_structure():
    files = discover_instances(DATA)
    if not files:
        pytest.skip("Montoya dataset not present")
    instance = load_original(files[0])
    assert instance.capacity_kwh == pytest.approx(16.0)
    assert instance.consumption_kwh_km == pytest.approx(0.125)
    assert instance.speed_kmh == pytest.approx(40.0)
    assert instance.horizon_hours == pytest.approx(10.0)
    assert instance.depot == 0
    assert instance.customers
    assert instance.stations


def test_enhanced_dataset_roundtrip():
    path = ENHANCED / "tc0c10s2ct1.json"
    if not path.is_file():
        pytest.skip("enhanced dataset not prepared")
    instance, meta = load_enhanced(path)
    assert instance.name == "tc0c10s2ct1"
    assert instance.capacity_kwh == pytest.approx(16.0)
    assert instance.vehicles >= 1
    assert meta.tou[-1]["end"] == 24.0
    dynamic = [n for n in instance.nodes.values() if n.kind == "customer" and n.release_hours > 0]
    assert dynamic, "expected some realtime customers"
    for node in dynamic:
        assert 0.0 < node.release_hours <= instance.horizon_hours


def test_apply_meta_sets_config():
    path = ENHANCED / "tc0c10s2ct1.json"
    if not path.is_file():
        pytest.skip("enhanced dataset not prepared")
    _, meta = load_enhanced(path)
    from evrp.config import Config
    config = Config()
    apply_meta(config, meta)
    assert config.tou == meta.tou
    assert config.deep_charge_cost == meta.degradation["deep_charge_cost"]