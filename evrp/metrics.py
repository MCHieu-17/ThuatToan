from evrp.config import Config
from evrp.domain import Action


def action_score(action: Action, config: Config) -> float:
    duration = action.end - action.start if action.kind in {"drive", "wait", "charge"} else 0.0
    degradation = action.deep_charge * config.deep_charge_cost \
        + action.deep_discharge * config.deep_discharge_cost
    return config.w_time * duration + config.w_electricity * action.electricity \
        + config.w_degradation * degradation


def summarize(actions: list[Action], config: Config) -> dict:
    times = {kind: sum(a.end - a.start for a in actions if a.kind == kind)
             for kind in ("drive", "wait", "charge", "service")}
    electricity = sum(a.electricity for a in actions)
    deep_charge = sum(a.deep_charge for a in actions)
    deep_discharge = sum(a.deep_discharge for a in actions)
    degradation = deep_charge * config.deep_charge_cost + deep_discharge * config.deep_discharge_cost
    total = times["drive"] + times["wait"] + times["charge"]
    return {"travel_hours": times["drive"], "wait_hours": times["wait"],
            "charge_hours": times["charge"], "service_hours": times["service"],
            "T_total": total, "C_electricity": electricity,
            "N_deep_charge": deep_charge, "N_deep_discharge": deep_discharge,
            "D_battery_degradation": degradation,
            "F": config.w_time * total + config.w_electricity * electricity
                 + config.w_degradation * degradation,
            "makespan_hours": max((a.end for a in actions), default=0.0)}
