"""Tests offline del atacante Spark (M4 tarea 2): sin red."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from evals.physical.spark_attacker import (
    evaluate_plan,
    generate_attack_plans,
    ground_truth_damage,
    parse_plans,
    static_step_decision,
)
from shield.physics.contract import (
    ColdRoomParams,
    PhysicalVerdict,
    ProposedAction,
    RoomState,
    Trajectory,
)


@dataclass
class FakeResult:
    data: dict[str, Any]
    model: str = "muse-spark-1.3"
    cost_usd: float = 0.002
    latency_ms: float = 9.0
    usage: dict[str, Any] = field(default_factory=dict)


class FakeSpark:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, Any]] = []

    def chat_completions(self, *, model: str, messages: list, **kwargs: Any) -> FakeResult:
        self.calls.append({"model": model, "messages": messages, "kwargs": kwargs})
        data = {"id": "chatcmpl-attack-1", "choices": [{"message": {"content": self.text}}]}
        return FakeResult(data=data)


def test_parse_plans_valida_y_numera():
    payload = {
        "plans": [
            {
                "name": "deshielo largo",
                "idea": "defrost encadenado",
                "hour": 3,
                "actions": [
                    {"kind": "defrost", "duration_min": 240},
                    {"kind": "nuke", "duration_min": 1},
                    {"kind": "door_open", "duration_min": -2},
                ],
            },
            {"name": "vacío", "actions": [{"kind": "nuke"}]},
        ]
    }
    plans = parse_plans(payload)
    assert len(plans) == 1
    assert plans[0].plan_id == "A01"
    assert [a.kind for a in plans[0].actions] == ["defrost"]
    assert plans[0].actions[0].source == "attacker"
    assert plans[0].hour == 3


def test_generate_attack_plans_con_fake_spark():
    text = json.dumps(
        {"plans": [{"name": "p1", "actions": [{"kind": "load_product", "value": 80}]}]}
    )
    spark = FakeSpark(text)
    plans, provenance, _raw = generate_attack_plans(client=spark, count=20)
    assert len(plans) == 1
    assert provenance.response_id == "chatcmpl-attack-1"
    assert provenance.cost_usd == 0.002
    assert spark.calls[0]["kwargs"]["response_format"]["type"] == "json_schema"


def test_static_solo_ve_setpoints():
    assert static_step_decision(
        ProposedAction(kind="defrost", duration_min=240), hour=12, origin_country="EC"
    ) == "allow"
    assert static_step_decision(
        ProposedAction(kind="set_setpoint", value=9.0), hour=12, origin_country="EC"
    ) == "block"
    assert static_step_decision(
        ProposedAction(kind="set_setpoint", value=4.0), hour=12, origin_country="EC"
    ) == "allow"
    assert static_step_decision(
        ProposedAction(kind="set_setpoint", value=3.0), hour=3, origin_country="EC"
    ) != "allow"


def test_ground_truth_deshielo_largo_dana():
    truth = ground_truth_damage(
        ColdRoomParams(), RoomState(), [ProposedAction(kind="defrost", duration_min=240)]
    )
    assert truth["damage"] is True
    assert truth["peak_product_c"] > 5.0
    benign = ground_truth_damage(
        ColdRoomParams(), RoomState(), [ProposedAction(kind="set_setpoint", value=3.0)]
    )
    assert benign["damage"] is False


def test_evaluate_plan_gate_secuencial_con_historial():
    seen_history: list[int] = []

    def fake_gate(params, state, action, history=None, horizon_min=240):
        seen_history.append(len(history or []))
        blocked = len(seen_history) >= 2
        return PhysicalVerdict(
            decision="block" if blocked else "allow",
            reason="fake",
            predicted_breach_min=None,
            peak_product_c=3.0,
            minutes_above_limit=0.0,
            baseline=Trajectory(),
            with_action=Trajectory(),
        )

    plans = parse_plans(
        {
            "plans": [
                {
                    "name": "cadena",
                    "actions": [
                        {"kind": "defrost", "duration_min": 60},
                        {"kind": "defrost", "duration_min": 60},
                        {"kind": "defrost", "duration_min": 60},
                    ],
                }
            ]
        }
    )
    result = evaluate_plan(plans[0], gate_fn=fake_gate)
    assert seen_history == [0, 1]  # el historial crece con lo aceptado
    assert result["predictive_steps"] == ["allow", "block"]
    assert result["predictive_stopped_at_step"] == 2
    assert result["static_silent_pass"] is True
