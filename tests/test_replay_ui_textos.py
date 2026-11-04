"""Textos de la repetición pública: idioma, escritura en vez de voz y escena de frío honesta."""

from __future__ import annotations

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


def _visible(page: str) -> str:
    return page.split("<script>")[0]


def test_replay_no_muestra_fila_spark_open_ni_microfono_ni_whatsapp():
    for lang in ("en", "es"):
        page = _visible(render_live_page(lang, replay=True))
        assert "sparkOpenRow" not in page and "Muse Spark Open" not in page
        assert "WhatsApp voice note" not in page and "Nota de voz de WhatsApp" not in page
        assert "Voice Transcribe transcript" not in page
    assert "Typed decision" in _visible(render_live_page("en", replay=True))
    assert "Decisión escrita" in _visible(render_live_page("es", replay=True))
    # En /live (no replay) la fila de procedencia de Spark Open sigue.
    assert "sparkOpenRow" in render_live_page("en")


def test_en_propone_frases_en_ingles_y_aprueban():
    page = render_live_page("en", replay=True)
    assert '"replay_phrase": "yes, rotate the warehouse token"' in page
    assert "sí, rota" not in _visible(page)
    cold = render_live_page("en", replay=True, scene="frio")
    assert '"replay_phrase": "yes, rotate refrigeration"' in cold

    cases = (("bodega", "yes, rotate the warehouse token"), ("frio", "yes, rotate refrigeration"))
    for scene, phrase in cases:
        run = ReplayRun(scene)
        for step in ("invoice", "count", "attack", "guardian"):
            assert run.step(step)["status"] == "ok", (scene, step)
        out = run.voice(phrase)
        assert out["status"] == "approved", (scene, out)
        assert out["input_mode"] == "typed"
        assert run.state()["voice"]["input_mode"] == "typed"


def test_frio_rotulado_como_simulacion_determinista_sin_incidente_real():
    en = _visible(render_live_page("en", replay=True, scene="frio"))
    assert "Deterministic simulation of the cold-chain policy; no model calls" in en
    assert "Guardian plan (deterministic)" in en
    assert "Guardian reasons (Muse Spark)" not in en
    assert "in the real incident" not in en
    assert "recording of a real live run" not in en
    es = _visible(render_live_page("es", replay=True, scene="frio"))
    assert "Simulación determinista de la política de cadena de frío" in es
    assert "Plan del guardián (determinista)" in es
    # Bodega sí es una corrida real grabada.
    assert "in the real incident" in _visible(render_live_page("en", replay=True))


def test_frio_trae_el_plan_en_ingles_para_la_pantalla_en():
    run = ReplayRun("frio")
    for step in ("invoice", "count", "attack"):
        run.step(step)
    out = run.step("guardian")
    plan_en = out["plan_en"]
    assert out["plan"]["steps"][0]["target"] == plan_en["steps"][0]["target"] == "refrigeracion"
    en_text = " ".join([plan_en["summary"], plan_en["reasoning"], plan_en["steps"][0]["reason"]])
    for spanish in ("Rotar", "fuera de", "Bodega", "Compras", "esperado"):
        assert spanish not in en_text


def test_errores_de_paso_traen_codigo_para_traducirlos(client):
    client.get("/")
    r = client.post("/replay/step/guardian")
    assert r.status_code == 409
    body = r.json()
    assert body["error_code"] == "needs_step" and body["need"] == "attack"
    v = client.post("/replay/voice", data={"typed": "yes"}).json()
    assert v["need"] == "guardian"
    es = render_live_page("es", replay=True)
    assert '"err_need_step": "primero corre el paso {n}"' in es
    assert "function stepErrorText" in es


def test_plainargs_serializa_objetos_y_corta():
    page = render_live_page("en", replay=True)
    assert 'typeof v === "object" ? JSON.stringify(v) : v' in page
    assert "text.slice(0, 299)" in page


def test_barra_fija_en_una_fila_en_movil():
    page = render_live_page("en", replay=True)
    assert "sticky-group sticky-sdk" in page
    assert ".sticky-inner{flex-wrap:nowrap" in page
    assert ".sticky-sdk,.sticky-cost,.sticky-label{display:none}" in page
