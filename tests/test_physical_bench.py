"""Tests del benchmark físico M2: esquema de casos y runner offline."""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

from evals.run_physical import SHIELDS, build_report, evaluate_cases, load_cases, render_markdown
from shield.physics.contract import ProposedAction, RoomState

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "physical" / "cases.json"
ACTION_FIELDS = {f.name for f in fields(ProposedAction)}
STATE_FIELDS = {f.name for f in fields(RoomState)}
KINDS = {"set_setpoint", "compressor_off", "defrost", "door_open", "load_product"}


def _cases() -> list[dict]:
    return load_cases(CASES_PATH)


def test_cases_schema_and_counts() -> None:
    """≥30 casos, ≥12 legítimos y ≥18 ataques, con campos del contrato."""
    raw = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    assert raw["label_note"] == "simulated"
    cases = raw["cases"]
    assert len(cases) >= 30
    legit = [c for c in cases if c["label"] == "legit"]
    attacks = [c for c in cases if c["label"] == "attack"]
    assert len(legit) >= 12
    assert len(attacks) >= 18
    assert len({c["id"] for c in cases}) == len(cases)
    for case in cases:
        assert case["label"] in {"legit", "attack"}
        assert case["vector"] and case["why"]
        assert set(case["state"]) <= STATE_FIELDS
        RoomState(**case["state"])
        assert set(case["action"]) <= ACTION_FIELDS
        assert case["action"]["kind"] in KINDS
        ProposedAction(**case["action"])
        for past in case["history"]:
            assert set(past) <= ACTION_FIELDS
            ProposedAction(**past)
        ctx = case["context"]
        assert 0 <= int(ctx["hour"]) <= 23 and ctx["origin_country"]


def test_required_legit_and_attack_families_present() -> None:
    """Las familias pedidas en la tarea están representadas."""
    cases = _cases()
    legit_vectors = {c["vector"] for c in cases if c["label"] == "legit"}
    attack_vectors = {c["vector"] for c in cases if c["label"] == "attack"}
    assert {
        "defrost_scheduled",
        "load_cold_product",
        "setpoint_in_range",
        "night_saving_safe",
        "door_open_short",
    } <= legit_vectors
    assert {
        "setpoint_out_of_range",
        "salami_drift",
        "compressor_off_after_hot_load",
        "defrost_long_door_open",
        "injected_document",
        "peak_hour",
        "combined",
    } <= attack_vectors


def test_runner_offline_none_and_static() -> None:
    """El runner corre sin red: none todo permite; static frena fuera de rango."""
    report = evaluate_cases(_cases(), shields=("none", "static"))
    assert report["label_note"] == "simulated"
    none_total = report["summary"]["none"]["total"]
    assert none_total["attacks_silent_pass"] == none_total["attacks_total"]
    assert none_total["false_blocks"] == 0
    static_rows = {r["case_id"]: r for r in report["results"] if r["shield"] == "static"}
    assert static_rows["A01"]["decision"] == "block"  # 8 °C fuera de rango
    assert static_rows["A18"]["decision"] == "block"  # dos señales blandas
    # Lo que el estático no ve: no conoce apagado de compresor ni deriva.
    assert static_rows["A10"]["decision"] == "allow"
    assert static_rows["A04"]["decision"] == "allow"  # cada paso salami en rango
    assert static_rows["L05"]["decision"] == "allow"
    assert "static" in render_markdown(evaluate_cases(_cases()[:1], shields=("static",)))


def test_addendum_defrost_override_separate() -> None:
    """Addendum congelado aparte: vector propio y reporte separado."""
    path = ROOT / "evals" / "physical" / "cases-addendum.json"
    addendum = load_cases(path)
    assert len(addendum) >= 5
    assert {c["vector"] for c in addendum} == {"defrost_override"}
    assert sum(c["label"] == "attack" for c in addendum) >= 4
    for case in addendum:
        RoomState(**case["state"])
        ProposedAction(**case["action"])
    report = build_report(_cases()[:1], addendum)
    assert report["cases"] == 1  # el addendum no suma a los totales
    assert report["addendum"]["cases"] == len(addendum)
    assert "defrost_override" in render_markdown(report)


def test_runner_predictive_unavailable_is_not_silent_pass() -> None:
    """Sin gate de M1 (o con él), unavailable nunca cuenta como allow."""
    report = evaluate_cases(_cases()[:2], shields=("predictive",))
    total = report["summary"]["predictive"]["total"]
    assert total["attacks_silent_pass"] <= total["attacks_total"]
    for row in report["results"]:
        assert row["decision"] in {"allow", "ask_owner", "block", "unavailable"}
    assert set(SHIELDS) == {"none", "static", "predictive"}
