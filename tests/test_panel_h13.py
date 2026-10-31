"""H13 tarea 1: lógica del panel (voz, cronómetro, sondas, fases, tick)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from channels.approvals import ApprovalBroker, ChannelApprover
from channels.voice import parse_voice_command
from channels.whatsapp import simulated_click_payload
from shield.agent import GuardianAgent, Plan, PlanStep
from shield.brand import BRAND, SUBTITLE
from web.app import _trim_statuses, build_replay_state, create_panel_app


def _make():
    state = build_replay_state()
    return state, TestClient(create_panel_app(state))


def _public(client: TestClient) -> dict:
    return client.get("/panel/state").json()


def _pending_id(client: TestClient) -> str:
    return _public(client)["pending"][0]["approval_id"]


class _RecordingActions:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def rotate_token(self, agent: str, approval_id: str) -> dict:
        self.calls.append(("rotate_token", agent))
        return {"status": "applied", "agent": agent}

    def rotate_upstream_key(self, provider: str, approval_id: str) -> dict:
        self.calls.append(("rotate_upstream_key", provider))
        return {"status": "applied", "provider": provider}

    def verify(self, target: str) -> dict:
        self.calls.append(("verify", target))
        return {"status": "ok", "target": target}

    def revoke(self, token_id: str, approval_id: str) -> dict:
        self.calls.append(("revoke", token_id))
        return {"status": "revoked", "token_id": token_id}


def test_steps_for_empty_approved_steps_executes_nothing():
    broker = ApprovalBroker()
    actions = _RecordingActions()
    guardian = GuardianAgent(actions=actions, approver=ChannelApprover(broker))
    guardian._plan = Plan(
        steps=[
            PlanStep("rotate_token", "bodega", "anomalía"),
            PlanStep("verify", "bodega", "salud", requires_approval=False),
        ],
        summary="prueba",
    )
    asked = guardian.tool_ask_owner()
    approval_id = asked["pending_approval_id"]
    broker.approve(approval_id, exclude_targets=["bodega"])
    assert broker.approved_steps_for(approval_id) == set()
    assert guardian._steps_for(approval_id) == set()
    report = guardian.execute_approved(approval_id)
    rotate_entries = [e for e in report.executed if e["action"] == "rotate_token"]
    assert rotate_entries == [
        {"action": "rotate_token", "target": "bodega", "status": "skipped"}
    ]
    assert ("rotate_token", "bodega") not in actions.calls


def test_voice_parser_english_reject_exclude_only():
    yes = parse_voice_command("yes, rotate everything except bodega")
    assert yes.action == "approve" and yes.exclude_targets == ["bodega"]
    but_not = parse_voice_command("yes, rotate all but not compras")
    assert but_not.action == "approve" and but_not.exclude_targets == ["compras"]
    assert parse_voice_command("go ahead").action == "approve"
    assert parse_voice_command("approve only compras").only_targets == ["compras"]
    assert parse_voice_command("rotate only bodega").only_targets == ["bodega"]
    for text in ("reject that", "cancel that", "deny it", "stop"):
        assert parse_voice_command(text).action == "reject", text


def test_voice_parser_negation_guard_never_approves():
    for text in ("no rota", "don't rotate", "do not rotate", "never rotate", "nunca rota"):
        assert parse_voice_command(text).action == "unknown", text
    # La negación junto a una palabra de rechazo sigue siendo rechazo.
    assert parse_voice_command("no, cancela eso").action == "reject"
    assert parse_voice_command("no, cancel that").action == "reject"
    # «menos»/«excepto» no son negación: se aprueba con exclusión.
    partial = parse_voice_command("sí, rota todo menos bodega")
    assert partial.action == "approve" and partial.exclude_targets == ["bodega"]


def test_trim_statuses_preserves_first_and_transition():
    source = [200] * 20 + [401] * 20
    trimmed = _trim_statuses(source)
    assert len(trimmed) == 12
    assert trimmed[0] == 200
    assert any(a == 200 and b == 401 for a, b in zip(trimmed, trimmed[1:], strict=False))
    assert source == [200] * 20 + [401] * 20  # función pura: no muta la entrada


def test_panel_voice_partial_requires_confirmation_then_confirm_in_other_request():
    state, client = _make()
    approval_id = _pending_id(client)
    original_token_id = state.token_store.get_token_id("bodega")

    first = client.post(
        "/panel/voice",
        data={"approval_id": approval_id, "transcript": "sí, rota todo menos Stripe"},
    )
    assert first.status_code == 200
    data = _public(client)
    notice = data["voice_notice"]
    assert notice["status"] == "confirmation_required"
    assert notice["will_run"] == ["bodega"]
    assert notice["excluded"] == ["stripe"]
    assert notice["unmatched"] == ["stripe"]
    assert data["phase"] == "awaiting_confirmation"
    assert data["executed"] == []
    assert not state.broker.is_approved(approval_id)
    assert state.token_store.get_token_id("bodega") == original_token_id
    assert data["attacker_statuses"][-1] == 200

    # La confirmación llega en otra petición HTTP distinta.
    confirmed = client.post("/panel/voice/confirm", data={"approval_id": approval_id})
    assert confirmed.status_code == 200
    after = _public(client)
    assert after["voice_notice"]["status"] == "approved"
    assert any(e.get("status") == "applied" for e in after["executed"])
    assert after["attacker_statuses"][-1] == 401
    assert after["phase"] == "contained"


def test_panel_voice_cancel_leaves_pending_and_executes_nothing():
    state, client = _make()
    approval_id = _pending_id(client)
    client.post(
        "/panel/voice",
        data={"approval_id": approval_id, "transcript": "sí, rota todo menos bodega"},
    )
    cancelled = client.post("/panel/voice/cancel", data={"approval_id": approval_id})
    assert cancelled.status_code == 200
    data = _public(client)
    assert data["voice_notice"]["status"] == "cancelled"
    assert data["phase"] == "pending"
    assert data["executed"] == []
    assert len(data["pending"]) == 1
    assert state.broker.get(approval_id).status == "pending"


def test_panel_voice_unknown_leaves_notice_and_touches_nothing():
    state, client = _make()
    approval_id = _pending_id(client)
    before = _public(client)
    payload = "<script>alert(1)</script> cuéntame un chiste"
    resp = client.post(
        "/panel/voice", data={"approval_id": approval_id, "transcript": payload}
    )
    assert resp.status_code == 200
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in resp.text
    assert "<script>alert(1)</script>" not in resp.text
    after = _public(client)
    assert after["voice_notice"]["status"] == "unknown_command"
    assert after["voice_notice"]["transcript"] == payload
    assert after["attempts_total"] == before["attempts_total"]
    assert after["attacker_statuses"] == before["attacker_statuses"]
    assert after["executed"] == []
    assert len(after["pending"]) == 1
    assert state.broker.get(approval_id).status == "pending"


def test_panel_voice_no_rota_does_not_approve():
    state, client = _make()
    approval_id = _pending_id(client)
    resp = client.post(
        "/panel/voice", data={"approval_id": approval_id, "transcript": "no rota"}
    )
    assert resp.status_code == 200
    data = _public(client)
    assert data["voice_notice"]["status"] == "unknown_command"
    assert not state.broker.is_approved(approval_id)
    assert data["executed"] == []
    assert len(data["pending"]) == 1


def test_panel_voice_rotate_all_except_bodega_confirmed_not_rotated():
    state, client = _make()
    approval_id = _pending_id(client)
    original_token_id = state.token_store.get_token_id("bodega")
    client.post(
        "/panel/voice",
        data={"approval_id": approval_id, "transcript": "sí, rota todo menos bodega"},
    )
    assert _public(client)["phase"] == "awaiting_confirmation"
    confirmed = client.post("/panel/voice/confirm", data={"approval_id": approval_id})
    assert confirmed.status_code == 200
    data = _public(client)
    assert state.broker.is_approved(approval_id)
    assert state.token_store.get_token_id("bodega") == original_token_id
    assert data["attacker_statuses"][-1] == 200
    assert data["phase"] == "not_rotated"
    assert not any(e.get("status") == "applied" for e in data["executed"])


def test_panel_reset_replay_restores_pending_attacker_200_and_new_token(monkeypatch):
    monkeypatch.setenv("DEMO", "replay")
    state, client = _make()
    _pending_id(client)
    old_raw = state.token_store.get_token("bodega")
    old_attacker = state.attacker_raw
    resp = client.post("/panel/reset")
    assert resp.status_code == 200
    data = _public(client)
    assert data["phase"] == "pending"
    assert len(data["pending"]) == 1
    assert data["attacker_statuses"] == [200]
    assert data["attempts_total"] == 1
    assert data["agent_statuses"]["bodega"] == [200]
    assert data["agent_statuses"]["compras"] == [200]
    assert state.token_store.get_token("bodega") != old_raw
    assert state.attacker_raw != old_attacker
    # El reloj vuelve a 0 y no arranca hasta el siguiente GET /.
    assert data["elapsed_s"] == 0.0 and data["clock_running"] is False
    assert client.get("/").status_code == 200
    assert _public(client)["clock_running"] is True


def test_panel_reset_forbidden_when_not_replay(monkeypatch):
    # H14: /panel/reset también se permite con DEMO=live; otros modos no.
    monkeypatch.setenv("DEMO", "live")
    _state, client = _make()
    assert client.post("/panel/reset").status_code == 200
    monkeypatch.setenv("DEMO", "other")
    assert client.post("/panel/reset").status_code == 403


def test_agents_stay_200_after_rotation_with_store_tokens_attacker_401():
    state, client = _make()
    approval_id = _pending_id(client)
    assert client.post(f"/panel/approve/{approval_id}").status_code == 200
    for name in ("bodega", "compras"):
        raw = state.token_store.get_token(name)
        assert raw and raw.startswith("shd_")
        resp = state.gateway.post(
            "/v1/chat/completions",
            json={"model": "muse-spark-1.3", "messages": [{"role": "user", "content": "x"}]},
            headers={"Authorization": f"Bearer {raw}", "X-Demo-Country": "EC"},
        )
        assert resp.status_code == 200, name
        assert state.probe_agent(name) == 200
    assert client.post("/panel/tick").status_code == 200
    data = _public(client)
    assert data["agent_statuses"]["bodega"][-1] == 200
    assert data["agent_statuses"]["compras"][-1] == 200
    assert data["attacker_statuses"][-1] == 401


def test_clock_does_not_start_without_get_and_stops_when_contained():
    _state, client = _make()
    before = _public(client)
    assert before["elapsed_s"] == 0.0 and before["clock_running"] is False
    assert before["contained_in_s"] is None
    assert client.get("/").status_code == 200
    assert _public(client)["clock_running"] is True
    approval_id = _pending_id(client)
    assert client.post(f"/panel/approve/{approval_id}").status_code == 200
    first = _public(client)
    second = _public(client)
    assert first["contained_in_s"] is not None
    assert first["phase"] == "contained"
    assert first["clock_running"] is False
    assert first["elapsed_s"] == first["contained_in_s"]
    assert second["elapsed_s"] == first["elapsed_s"]


def test_clock_rejection_does_not_stop_it():
    _state, client = _make()
    assert client.get("/").status_code == 200
    approval_id = _pending_id(client)
    assert client.post(f"/panel/reject/{approval_id}").status_code == 200
    data = _public(client)
    assert data["phase"] == "rejected"
    assert data["contained_in_s"] is None
    assert data["clock_running"] is True
    assert data["attacker_statuses"][-1] == 200


def test_trim_keeps_200_to_401_after_50_probes():
    state, client = _make()
    approval_id = _pending_id(client)
    assert client.post(f"/panel/approve/{approval_id}").status_code == 200
    before_total = _public(client)["attempts_total"]
    for _ in range(50):
        assert state.probe_attacker() == 401
    data = _public(client)
    assert data["attempts_total"] == before_total + 50
    assert len(data["attacker_statuses"]) <= 12
    assert data["attacker_statuses"][0] == 200
    pairs = zip(data["attacker_statuses"], data["attacker_statuses"][1:], strict=False)
    assert any(a == 200 and b == 401 for a, b in pairs)
    assert data["attacker_timeline"].startswith("200 → 401")


def test_double_approval_idempotent_and_unknown_id_400():
    state, client = _make()
    approval_id = _pending_id(client)
    assert client.post(f"/panel/approve/{approval_id}").status_code == 200
    rotated_token_id = state.token_store.get_token_id("bodega")
    executed_before = _public(client)["executed"]
    second = client.post(f"/panel/approve/{approval_id}")
    assert second.status_code == 200
    assert state.token_store.get_token_id("bodega") == rotated_token_id
    assert _public(client)["executed"] == executed_before
    missing = client.post("/panel/approve/pend_no_existe")
    assert missing.status_code == 400
    assert "pend_no_existe" in missing.text


def test_whatsapp_simulated_approval_executes_once_on_tick():
    state, client = _make()
    approval_id = _pending_id(client)
    original_token_id = state.token_store.get_token_id("bodega")
    payload = simulated_click_payload(
        approval_id=approval_id, action="approve", message_id="wamid-h13-1"
    )
    clicked = client.post("/webhook/whatsapp", json=payload)
    assert clicked.status_code == 200
    assert clicked.json()["results"][0]["status"] == "approved"
    # Aprobado por WhatsApp, pero todavía sin ejecutar.
    before_tick = _public(client)
    assert before_tick["executed"] == []
    assert state.token_store.get_token_id("bodega") == original_token_id

    assert client.post("/panel/tick").status_code == 200
    after = _public(client)
    assert any(e.get("status") == "applied" for e in after["executed"])
    assert after["attacker_statuses"][-1] == 401
    assert after["agent_statuses"]["bodega"][-1] == 200
    rotated_token_id = state.token_store.get_token_id("bodega")
    assert rotated_token_id != original_token_id

    # Un segundo tick no vuelve a rotar.
    assert client.post("/panel/tick").status_code == 200
    assert state.token_store.get_token_id("bodega") == rotated_token_id


def test_no_raw_token_appears_in_page_or_state_after_rotation():
    state, client = _make()
    approval_id = _pending_id(client)
    assert client.post(f"/panel/approve/{approval_id}").status_code == 200
    raws = {
        state.token_store.get_token("bodega"),
        state.token_store.get_token("compras"),
        state.attacker_raw,
    }
    assert all(raws)
    home = client.get("/")
    assert home.status_code == 200
    state_text = client.get("/panel/state").text
    for raw in raws:
        assert raw not in home.text
        assert raw not in state_text
    assert "attacker_raw" not in _public(client)


def test_panel_no_external_resources_brand_and_replay_label():
    import re

    _state, client = _make()
    home = client.get("/")
    assert home.status_code == 200
    refs = re.findall(r"(?:src|href)=['\"]([^'\"]+)['\"]", home.text)
    assert refs, "la página debe tener al menos el favicon"
    assert all(not r.startswith(("http://", "https://", "//")) for r in refs), refs
    assert "unpkg" not in home.text and "hx-" not in home.text
    assert (
        "Built on Meta's Muse models; independent project, "
        "not affiliated with or endorsed by Meta." in home.text
    )
    assert "Replay — test tokens, fake upstream, no real keys" in home.text
    assert f"{BRAND} — {SUBTITLE}" in home.text


def test_panel_reset_version_keeps_rising_so_live_does_not_204(monkeypatch):
    monkeypatch.setenv("DEMO", "replay")
    _state, client = _make()
    before = _public(client)["version"]
    assert client.post("/panel/reset").status_code == 200
    after = _public(client)["version"]
    assert after == before + 1
    changed = client.get("/panel/live", params={"v": before})
    assert changed.status_code == 200
    assert 'id="app"' in changed.text


def test_panel_approve_probes_bodega_without_another_click():
    _state, client = _make()
    before = _public(client)["agent_statuses"]["bodega"]
    approval_id = _pending_id(client)
    assert client.post(f"/panel/approve/{approval_id}").status_code == 200
    after = _public(client)["agent_statuses"]["bodega"]
    assert len(after) > len(before)
    assert after[-1] == 200


def test_panel_autotick_stops_after_12_pending_and_3_after_contained():
    _state, client = _make()
    start = _public(client)["attempts_total"]
    for _ in range(12):
        assert client.post("/panel/tick").status_code == 200
    stopped = _public(client)
    assert stopped["attempts_total"] == start + 12
    assert stopped["autotick"] == 0
    assert client.post("/panel/tick").status_code == 200
    assert _public(client)["attempts_total"] == stopped["attempts_total"]

    # Tras contener quedan 3 ticks más y también se detiene.
    state2, client2 = _make()
    approval_id = _pending_id(client2)
    assert client2.post(f"/panel/approve/{approval_id}").status_code == 200
    assert _public(client2)["phase"] == "contained"
    base = _public(client2)["attempts_total"]
    for _ in range(3):
        assert client2.post("/panel/tick").status_code == 200
    done = _public(client2)
    assert done["attempts_total"] == base + 3
    assert done["autotick"] == 0
    assert state2.autotick_ticks == 3
    assert client2.post("/panel/tick").status_code == 200
    assert _public(client2)["attempts_total"] == done["attempts_total"]


def test_panel_transcript_script_is_escaped_in_page():
    _state, client = _make()
    approval_id = _pending_id(client)
    payload = "<script>alert(1)</script> hola"
    resp = client.post(
        "/panel/voice", data={"approval_id": approval_id, "transcript": payload}
    )
    assert resp.status_code == 200
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in resp.text
    assert "<script>alert(1)</script>" not in resp.text


def test_attempt_singular_and_plural_en_es():
    _state, client = _make()
    assert _public(client)["attempts_total"] == 1
    home_en = client.get("/").text
    assert "1 attempt" in home_en and "1 attempts" not in home_en
    home_es = client.get("/?lang=es").text
    assert "1 intento" in home_es and "1 intentos" not in home_es
    assert client.post("/panel/attacker/probe").status_code == 200
    assert _public(client)["attempts_total"] == 2
    assert "2 attempts" in client.get("/?lang=en").text
    assert "2 intentos" in client.get("/?lang=es").text


def test_support_line_per_phase_en_es():
    # pending: la anomalía actual.
    _state, client = _make()
    pending_en = client.get("/").text
    assert "New country:" in pending_en
    assert "Warehouse's old token is revoked." not in pending_en
    pending_es = client.get("/?lang=es").text
    assert "País nuevo:" in pending_es

    # contained
    state2, client2 = _make()
    approval_id = _pending_id(client2)
    assert client2.post(f"/panel/approve/{approval_id}").status_code == 200
    assert _public(client2)["phase"] == "contained"
    contained_en = client2.get("/").text
    assert (
        "Warehouse's old token is revoked. The attacker now gets 401."
        in contained_en
    )
    contained_es = client2.get("/?lang=es").text
    assert (
        "El token viejo de Bodega quedó revocado. El atacante ahora recibe 401."
        in contained_es
    )
    assert state2.phase == "contained"

    # rejected
    _state3, client3 = _make()
    approval_id3 = _pending_id(client3)
    assert client3.post(f"/panel/reject/{approval_id3}").status_code == 200
    assert _public(client3)["phase"] == "rejected"
    assert "The attacker still gets 200." in client3.get("/").text
    assert "El atacante sigue recibiendo 200." in client3.get("/?lang=es").text

    # not_rotated: aprobar por voz excluyendo a bodega y confirmar.
    _state4, client4 = _make()
    approval_id4 = _pending_id(client4)
    client4.post(
        "/panel/voice",
        data={
            "approval_id": approval_id4,
            "transcript": "sí, rota todo menos bodega",
        },
    )
    assert _public(client4)["phase"] == "awaiting_confirmation"
    # awaiting_confirmation también muestra la anomalía actual.
    assert "New country:" in client4.get("/").text
    assert client4.post(
        "/panel/voice/confirm", data={"approval_id": approval_id4}
    ).status_code == 200
    assert _public(client4)["phase"] == "not_rotated"
    assert "The attacker still gets 200." in client4.get("/").text
    assert "El atacante sigue recibiendo 200." in client4.get("/?lang=es").text


def test_decisions_html_only_8_most_recent_newest_first_with_total():
    from web.app import _decisions_html

    state, client = _make()
    for _ in range(10):
        state.probe_agent("bodega")
    calls = state.registry.list_calls()
    total = len(calls)
    assert total > 8
    html_en = _decisions_html(state, "en")
    assert html_en.count("<li>") == 8
    assert f"{total} in total" in html_en
    # La primera fila corresponde a la llamada más reciente registrada.
    last = calls[-1]
    first_li = html_en.split("<li>", 1)[1].split("</li>", 1)[0]
    assert last.model in first_li
    assert last.ts.strftime("%H:%M:%S") in first_li
    html_es = _decisions_html(state, "es")
    assert html_es.count("<li>") == 8
    assert f"{total} en total" in html_es
    # Solo cambia el HTML: el estado público sigue con todas las llamadas.
    assert len(_public(client)["calls"]) == total


def test_advisory_line_from_file_en_es_and_missing_file(monkeypatch, tmp_path):
    import web.app as panel

    _state, client = _make()
    home_en = client.get("/").text
    assert (
        "Advisory on file: Railway: anomalous activity on environment "
        "variables, 21 Oct 2026 · blog.railway.com · "
        "not matched to an asset in this replay; the alert comes from "
        "the new-country signal." in home_en
    )
    assert "https://blog.railway.com" not in home_en
    assert "guardian detected" not in home_en.lower()
    home_es = client.get("/?lang=es").text
    assert (
        "Aviso en archivo: Railway 21-oct-2026: actividad anómala en "
        "variables de entorno, 21 oct 2026 · blog.railway.com · "
        "sin coincidencia con un activo en este replay; "
        "la alerta viene de la señal de país nuevo." in home_es
    )
    # Si falta el archivo no se muestra nada y no falla.
    monkeypatch.setattr(panel, "_ADVISORY_PATH", tmp_path / "no-existe.json")
    assert panel._advisory_line("en") == ""
    assert panel._advisory_line("es") == ""
    assert client.get("/").status_code == 200
    assert "Advisory on file:" not in client.get("/").text


def test_live_version_and_post_fragment_vs_full_page():
    _state, client = _make()
    version = _public(client)["version"]
    unchanged = client.get("/panel/live", params={"v": version})
    assert unchanged.status_code == 204

    fragment = client.post("/panel/tick", headers={"X-Panel-Fetch": "1"})
    assert fragment.status_code == 200
    assert 'id="app"' in fragment.text
    assert "<!doctype html>" not in fragment.text.lower()

    new_version = _public(client)["version"]
    assert new_version > version
    changed = client.get("/panel/live", params={"v": version})
    assert changed.status_code == 200 and 'id="app"' in changed.text
    assert client.get("/panel/live", params={"v": new_version}).status_code == 204

    full = client.post("/panel/tick")
    assert full.status_code == 200
    assert "<!doctype html>" in full.text.lower()


def test_restart_from_open_page_starts_clock_so_time_is_not_zero(monkeypatch):
    monkeypatch.setenv("DEMO", "replay")
    state, client = _make()
    client.get("/")
    client.post("/panel/reset", headers={"X-Panel-Fetch": "1"})
    assert state.clock_started_at is not None
    assert client.get("/panel/state").json()["clock_running"] is True
