from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from evrp.config import Config
from evrp.io.montoya import discover_instances, load_instance
from evrp.scenario import generate_scenario


def test_units_and_namespace(tmp_path, demo):
    tree = ET.parse(demo.source)
    for element in tree.getroot().iter():
        if element.tag in {"battery_capacity", "consumption_rate", "battery_level"}:
            element.text = str(float(element.text) / 1000)
        element.tag = "{urn:test}" + element.tag
    target = tmp_path / "converted.xml"
    tree.write(target)
    converted = load_instance(target, "kWh")
    assert converted.capacity_kwh == demo.capacity_kwh == 5
    assert converted.consumption_kwh_km == demo.consumption_kwh_km == .4
    assert converted.curves == demo.curves
    assert converted.travel(0, 1) == pytest.approx((.4, 1.6))


def test_invalid_curve_rejected(tmp_path, demo):
    text = Path(demo.source).read_text().replace("<charging_time>0.75</charging_time>",
                                               "<charging_time>0.2</charging_time>")
    file = tmp_path / "invalid.xml"
    file.write_text(text)
    with pytest.raises(ValueError, match="strictly increasing"):
        load_instance(file)


def test_discover_recursive_uppercase(tmp_path, demo):
    nested = tmp_path / "nested"
    nested.mkdir()
    file = nested / "x.XML"
    file.write_text(Path(demo.source).read_text())
    assert discover_instances(tmp_path) == [file]


def test_real_montoya_when_present():
    root = Path(__file__).parents[1] / "data/montoya-et-al-2017"
    files = discover_instances(root)
    if not files:
        pytest.skip("Original XML dataset is not bundled")
    for file in files:
        instance = load_instance(file)
        assert instance.capacity_kwh == 16
        assert instance.speed_kmh == 40
        assert instance.consumption_kwh_km == .125
        assert len(instance.customers) in {10, 20, 40, 80, 160, 320}


@pytest.mark.parametrize("kwargs", [
    {"w_time": -1}, {"station_ports": 1.5}, {"soc_step": 0},
    {"reserve_soc": .2}, {"power_fractions": [0]}, {"w_time": 0,"w_electricity": 0,"w_degradation": 0},
    {"tou": [{"start": 1,"end": 24,"price": .1}]}, {"solver_budget_seconds": float("nan")},
])
def test_bad_configuration(kwargs):
    with pytest.raises(ValueError):
        Config(**kwargs).validate()


def test_scenario_reproducible_and_online(demo, config):
    a, b = generate_scenario(demo, config, 42), generate_scenario(demo, config, 42)
    assert a.releases == b.releases
    assert len([t for t in a.releases.values() if t > 0]) == round(len(demo.customers) * config.dynamic_fraction)
    for at in [0, .1, .5, 1]:
        assert all(a.releases[n] <= at + 1e-9 for n in a.known(at))
