"""Revisión del PR #36 (4-nov): grabación intacta, dos pestañas, foto propia y textos."""

from __future__ import annotations

import json
import re
import time

import pytest
from fastapi.testclient import TestClient

from web.app import create_panel_app
from web.live_page import render_live_page
from web.replay_run import ReplayRun


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DEMO", "replay")
    monkeypatch.setenv("SHIELD_PANEL_SESSIONS", "1")
    monkeypatch.setenv("SHIELD_REPLAY_HOME", "1")
    return TestClient(create_panel_app())


def _until_approved(run: ReplayRun) -> None:
    for step in ("invoice", "count", "attack", "guardian"):
        assert run.step(step)["status"] == "ok", step
    assert run.voice("yes, rotate the warehouse token")["status"] == "approved"


# -- 4: contain no muta la grabación; un segundo contain se rechaza ------------------
def test_second_contain_is_rejected_and_recorded_time_stays_47s():
    run = ReplayRun("bodega")
    _until_approved(run)
    first = run.step("contain")
    assert first["recorded_contained_in_s"] == pytest.approx(47.021)
    time.sleep(0.05)
    again = run.step("contain")
    assert again["status"] == "error"
    assert again["error_code"] == "contained"
    state = run.state()
    assert state["contained_in_s"] == first["contained_in_s"]
    assert state["results"]["contain"]["recorded_contained_in_s"] == pytest.approx(47.021)
    # La grabación cargada sigue con su valor original.
    assert run._recorded["results"]["contain"]["contained_in_s"] == pytest.approx(47.021)
    assert "recorded_contained_in_s" not in run._recorded["results"]["contain"]
    assert run._recorded["results"]["guardian"].get("approval_id") != run.approval_id


def test_second_contain_over_http_answers_409_contained(client):
    client.get("/")
    for step in ("invoice", "count", "attack", "guardian"):
        assert client.post(f"/replay/step/{step}").status_code == 200
    client.post("/replay/voice", data={"typed": "yes, rotate the warehouse token"})
    assert client.post("/replay/step/contain").status_code == 200
    r = client.post("/replay/step/contain")
    assert r.status_code == 409
    assert r.json()["error_code"] == "contained"
    contain = client.get("/replay/state").json()["results"]["contain"]
    assert contain["recorded_contained_in_s"] == pytest.approx(47.021)


# -- 5: dos pestañas con la misma cookie ---------------------------------------------
def test_scene_changed_in_another_tab_answers_409_stale(client):
    client.get("/?scene=bodega")
    rid = client.get("/replay/state?scene=bodega").json()["run_id"]
    assert client.post(f"/replay/step/invoice?scene=bodega&run={rid}").status_code == 200
    client.get("/?scene=frio")  # la otra pestaña
    for method, path in (
        ("post", "/replay/step/attack"),
        ("get", "/replay/state"),
        ("post", "/replay/start"),
        ("post", "/replay/voice/confirm"),
        ("post", "/replay/voice/cancel"),
    ):
        r = getattr(client, method)(f"{path}?scene=bodega&run={rid}")
        assert r.status_code == 409, path
        assert r.json() == {**r.json(), "status": "stale", "error_code": "scene_changed"}
    r = client.post("/replay/voice?scene=bodega", data={"typed": "yes"})
    assert r.status_code == 409 and r.json()["error_code"] == "scene_changed"
    # La escena de frío no recibió nada de la pestaña vieja.
    state = client.get("/replay/state?scene=frio").json()
    assert state["scene"] == "frio" and state["results"] == {}


def test_new_run_in_another_tab_answers_409_run_changed(client):
    client.get("/?scene=bodega")
    rid = client.get("/replay/state?scene=bodega").json()["run_id"]
    client.post("/replay/reset?scene=bodega")  # «New run» en la otra pestaña
    r = client.post(f"/replay/step/invoice?scene=bodega&run={rid}")
    assert r.status_code == 409
    assert r.json()["status"] == "stale" and r.json()["error_code"] == "run_changed"


def test_reset_with_scene_starts_a_run_of_that_scene(client):
    client.get("/?scene=frio")
    fresh = client.post("/replay/reset?scene=bodega").json()
    assert fresh["scene"] == "bodega"


def test_without_scene_or_run_params_nothing_changes(client):
    client.get("/")
    assert client.post("/replay/step/invoice").status_code == 200
    assert client.get("/replay/state").status_code == 200


def test_page_sends_scene_and_run_and_shows_reload_notice():
    for lang in ("en", "es"):
        for scene in ("bodega", "frio"):
            page = render_live_page(lang, replay=True, scene=scene)
            assert "function replayPath(path)" in page
            assert 'new URLSearchParams({scene: SCENE})' in page
            assert 'q.set("run", RUN_ID)' in page
            assert "showStaleNotice()" in page
            assert '"scene_changed"' in page
    texts = {
        lang: json.loads(re.search(r"const TEXT = (\{.*?\});\n", render_live_page(lang)).group(1))
        for lang in ("en", "es")
    }
    assert texts["en"]["reload"] == "Reload" and texts["es"]["reload"] == "Recargar"
    assert "Otra pestaña" in texts["es"]["stale_page"]


# -- 6: sin foto propia en la repetición ---------------------------------------------
def test_replay_page_has_no_own_photo_picker_but_live_does():
    for lang in ("en", "es"):
        assert "id='ownPhoto'" not in render_live_page(lang, replay=True, scene="bodega")
        assert "id='ownPhoto'" in render_live_page(lang)


def test_uploaded_photo_in_replay_is_ignored_with_explicit_notice(client):
    client.get("/")
    r = client.post(
        "/replay/step/count", files={"file": ("mine.png", b"\x89PNG\r\n\x1a\nfake", "image/png")}
    )
    assert r.status_code == 409
    body = r.json()
    assert body["error_code"] == "own_photo_not_counted"
    assert "ignored" in body["error"]
    assert "count" not in client.get("/replay/state").json()["results"]  # sin conteo grabado
    assert client.post("/replay/step/count").status_code == 200  # sin archivo, sigue igual


# -- 7: botón principal ----------------------------------------------------------------
def test_run_until_disabled_when_contained_and_enabled_on_new_run():
    page = render_live_page("en", replay=True)
    band = page.split("function updateBand(state)")[1][:400]
    assert "runUntil.disabled = isContained(state)" in band
    clear_run = page.split("function clearRun()")[1][:1400]
    assert "runUntil.disabled = false" in clear_run
    contained = page.split("function isContained(state)")[1][:200]
    assert 'c.status === "ok" || c.status === "contained"' in contained


# -- 8: «approved» traducido -----------------------------------------------------------
def test_es_never_shows_raw_approved_status():
    page = render_live_page("es", replay=True)
    assert '"approved": "aprobado"' in page
    assert 'TEXT.ok + ": " + (r.status' not in page
    assert 'TEXT.ok + ": " + (data.status' not in page
    assert 'textContent = data.status || ""' not in page
    assert page.count("statusWord(") >= 6


# -- 9: ids de respuesta sin «[REDACTED:phone]» ----------------------------------------
def test_response_ids_show_ellipsis_not_phone_marker():
    run = ReplayRun("bodega")
    _until_approved(run)
    run.step("contain")
    dump = json.dumps(run.state()) + run.export()
    assert "[REDACTED:phone]" not in dump
    ids = [
        r.get(k) for r in run.state()["provenance"] for k in ("response_id", "upstream_request_id")
    ]
    assert "chatcmpl-01a19d80-…-8ea5-abd08b2a7252" in ids
    assert "a49e883d-…-838f-45576e2e8830" in ids


# -- 10: escena de frío y nota grabada -------------------------------------------------
def test_cold_scene_labels():
    for lang, why, accepted in (
        ("en", "Why this plan", "token accepted, action blocked by policy"),
        ("es", "Por qué este plan", "token aceptado, acción bloqueada por la política"),
    ):
        cold = render_live_page(lang, replay=True, scene="frio")
        texts = json.loads(re.search(r"const TEXT = (\{.*?\});\n", cold).group(1))
        assert texts["plan_reasoning"] == why
        assert texts["cold_token_accepted"] == accepted
        assert "id='coldAttackNote'" in cold
        assert texts["demo_inventory"] not in cold.split("<body")[1].split("<script")[0]
        bodega = render_live_page(lang, replay=True, scene="bodega")
        assert "id='coldAttackNote'" not in bodega
        assert json.loads(re.search(r"const TEXT = (\{.*?\});\n", bodega).group(1))[
            "plan_reasoning"
        ] in ("Model reasoning", "Razonamiento del modelo")


def test_recorded_run_note_is_dated_and_spaced():
    en = render_live_page("en", replay=True)
    es = render_live_page("es", replay=True)
    assert '"recorded_live_run": "recorded live run (2 Nov)"' in en
    assert '"recorded_live_run": "corrida en vivo grabada (2 nov)"' in es
    assert ".key-result .recorded-run{display:inline-block;margin-left:14px" in en
