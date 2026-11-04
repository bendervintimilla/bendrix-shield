"""Testigo de cámara en el autopiloto: endurece, nunca relaja (sin red)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from shield.autopilot import (
    camera_event,
    detect,
    from_cold_room,
    harden_decision,
    run_pipeline,
)
from shield.autopilot.detect import SEVERITY_ORDER
from shield.witness import WitnessObservation, WitnessRegistry

T0 = datetime(2026, 11, 4, 20, 0, tzinfo=UTC)


def _cam(people: int, at: datetime = T0, *, room: str = "camara", ok: bool = True):
    return WitnessObservation(
        camera="cam-frio", site="madrid", room=room, captured_at=at.isoformat(),
        people=people, door_open=None, source="fixture",
        error=None if ok else "RuntimeError: sam caído")


def _cmd(action: str = "set_setpoint", *, source: str = "agent", at: datetime | None = None,
         room: str | None = "camara", **values):
    raw = {"action": action, "actor": "agent:frio-bot", "target": "camara",
           "source": source, "ts": (at or T0 + timedelta(seconds=30)).isoformat(),
           "site": "madrid", "value": 4.0, **values}
    if room is not None:
        raw["room"] = room
    return from_cold_room(raw)


def _kinds(findings):
    return {f.kind: f.severity for f in findings}


def test_camera_event_adapter():
    ev = camera_event(_cam(2))
    assert ev.app == "camera" and ev.action == "observation" and ev.target == "camara"
    assert ev.values["people"] == 2 and ev.values["ok"] is True and ev.ts == T0
    assert "redacted_image" not in ev.values
    assert camera_event(_cam(2).public()).values == ev.values


def test_remote_command_with_nobody_in_room_is_high():
    kinds = _kinds(detect([camera_event(_cam(0)), _cmd()]))
    assert kinds["unattended_remote_physical_command"] == "high"


def test_remote_command_with_people_present_has_no_witness_finding():
    kinds = _kinds(detect([camera_event(_cam(2)), _cmd()]))
    assert not {"unattended_remote_physical_command", "on_site_claim_contradicted",
                "on_site_claim_unverified"} & set(kinds)


@pytest.mark.parametrize("action", ["defrost", "compressor_off", "door_open"])
def test_all_physical_actions_are_covered(action):
    kinds = _kinds(detect([camera_event(_cam(0)), _cmd(action, duration_min=10)]))
    assert "unattended_remote_physical_command" in kinds


def test_on_site_claim_contradicted_is_critical():
    kinds = _kinds(detect([camera_event(_cam(0)), _cmd(source="on_site")]))
    assert kinds["on_site_claim_contradicted"] == "critical"
    assert "unattended_remote_physical_command" not in kinds


def test_on_site_with_people_is_clean():
    kinds = _kinds(detect([camera_event(_cam(1)), _cmd(source="on_site")]))
    assert not any(k.startswith("on_site") or k.startswith("unattended") for k in kinds)


def test_stale_witness_fails_closed():
    old = camera_event(_cam(3, T0 - timedelta(minutes=10)))
    assert "unattended_remote_physical_command" in _kinds(detect([old, _cmd()]))
    assert _kinds(detect([old, _cmd(source="on_site")]))["on_site_claim_unverified"] == "high"


def test_failed_sam_witness_is_stale():
    bad = camera_event(_cam(2, ok=False))
    assert "unattended_remote_physical_command" in _kinds(detect([bad, _cmd()]))


def test_only_future_observation_counts_as_stale():
    future = camera_event(_cam(2, T0 + timedelta(minutes=5)))
    assert "unattended_remote_physical_command" in _kinds(detect([future, _cmd()]))


def test_room_without_witness_keeps_previous_behaviour():
    other_room = camera_event(_cam(0, room="sala"))
    before = _kinds(detect([_cmd()]))
    after = _kinds(detect([other_room, _cmd()]))
    assert before == after
    assert "unattended_remote_physical_command" not in after


def test_registry_witness_and_staleness():
    reg = WitnessRegistry()
    reg.update(_cam(0))
    assert "unattended_remote_physical_command" in _kinds(detect([_cmd()], witness=reg))
    reg2 = WitnessRegistry()
    reg2.update(_cam(1))
    assert "unattended_remote_physical_command" not in _kinds(detect([_cmd()], witness=reg2))
    late = _cmd(at=T0 + timedelta(seconds=500))
    assert "unattended_remote_physical_command" in _kinds(detect([late], witness=reg2))
    reg3 = WitnessRegistry()
    reg3.register("madrid", "camara")  # testigo declarado, sin dato
    assert "unattended_remote_physical_command" in _kinds(detect([_cmd()], witness=reg3))


def test_witness_raises_incident_severity_in_pipeline():
    events = [camera_event(_cam(0)), _cmd(source="on_site")]
    incident, result = run_pipeline(events)
    assert incident.severity == "critical"
    assert result.scope_level in ("app", "campaign", "global")
    baseline_incident, _ = run_pipeline([_cmd(source="on_site")])
    assert SEVERITY_ORDER[incident.severity] >= SEVERITY_ORDER[baseline_incident.severity]


@pytest.mark.parametrize("decision,floor,expected", [
    ("allow", None, "allow"),
    ("allow", "ask_owner", "ask_owner"),
    ("ask_owner", "ask_owner", "ask_owner"),
    ("block", "ask_owner", "block"),  # nunca relaja
    ("ask_owner", "block", "block"),
    ("block", None, "block"),
])
def test_harden_decision_never_relaxes(decision, floor, expected):
    assert harden_decision(decision, floor) == expected


def test_witness_never_removes_physics_findings():
    # Comando físico peligroso: lo que detectaba la física sigue ahí con testigo.
    cmd = _cmd("compressor_off", duration_min=600)
    without = _kinds(detect([cmd]))
    with_witness = _kinds(detect([camera_event(_cam(2)), cmd]))
    for kind, sev in without.items():
        assert with_witness.get(kind) == sev
