"""C2491: la URL pública abre la pantalla nueva (esfera) corriendo la repetición grabada."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.app import create_panel_app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DEMO", "replay")
    monkeypatch.setenv("SHIELD_PANEL_SESSIONS", "1")
    monkeypatch.setenv("SHIELD_REPLAY_HOME", "1")
    return TestClient(create_panel_app())


def _run_until_owner(c: TestClient) -> None:
    for step in ("invoice", "count", "attack", "guardian"):
        r = c.post(f"/replay/step/{step}")
        assert r.status_code == 200, (step, r.text)


def test_raiz_abre_la_esfera_en_repeticion_con_en_es_y_dos_escenas(client):
    es = client.get("/?lang=es")
    assert es.status_code == 200
    for needle in (
        "sphereCanvas",
        "Correr hasta que el dueño decida",
        "Tu cuadrilla está trabajando.",
        "Tiempo real al primer 401",
        "Cadena de frío",
        "const REPLAY = true",
    ):
        assert needle in es.text, needle
    assert 'aria-disabled="true"' in es.text or "aria-disabled='true'" in es.text  # En vivo
    assert "Someone is using Warehouse" not in es.text
    en = client.get("/?lang=en&scene=frio")
    assert "Cold chain" in en.text and 'const SCENE = "frio"' in en.text


def test_en_vivo_sigue_cerrado_en_la_publica(client):
    assert client.post("/live/start").status_code == 403
    assert client.post("/live/step/invoice").status_code == 403
    assert client.post("/live/voice").status_code == 403
    assert client.get("/docs").status_code == 404
    assert client.get("/live").status_code == 200  # solo la pantalla de aviso, sin llamar a nada
    assert client.post("/webhook/whatsapp", json={}).status_code in (404, 405)


def test_bodega_corre_la_repeticion_completa_con_aprobacion_real(client):
    client.get("/")
    _run_until_owner(client)
    # Sin aprobar no se puede contener.
    assert client.post("/replay/step/contain").status_code in (200, 409)
    state = client.get("/replay/state").json()
    assert "contain" not in state["results"]
    unknown = client.post("/replay/voice", data={"typed": "hola"}).json()
    assert unknown["status"] == "unknown_command"
    ok = client.post("/replay/voice", data={"typed": "sí, rota el token de bodega"}).json()
    assert ok["status"] == "approved"
    done = client.post("/replay/step/contain").json()
    assert done["attacker_after"] == [401] and done["compras_status"] == 200
    state = client.get("/replay/state").json()
    assert state["total_cost_usd"] == 0
    assert state["contained_in_s"] is not None


def test_frio_corre_y_solo_rota_refrigeracion(client):
    client.get("/?scene=frio")
    _run_until_owner(client)
    state = client.get("/replay/state").json()
    assert state["scene"] == "frio"
    attacks = state["results"]["attack"]["attacks"]
    assert [a["decision"] for a in attacks] == ["block", "block"]
    assert state["results"]["guardian"]["plan"]["steps"][0]["target"] == "refrigeracion"
    ok = client.post("/replay/voice", data={"typed": "sí, rota refrigeración"}).json()
    assert ok["status"] == "approved"
    done = client.post("/replay/step/contain").json()
    assert done["attacker_after"] == [401]
    assert (done["refrigeracion_status"], done["bodega_status"], done["compras_status"]) == (
        200,
        200,
        200,
    )


def test_sesiones_por_visitante_no_se_pisan(client):
    other = TestClient(client.app)
    client.get("/")
    other.get("/")
    client.post("/replay/step/invoice")
    assert "invoice" in client.get("/replay/state").json()["results"]
    assert other.get("/replay/state").json()["results"] == {}


def test_aprobacion_de_la_repeticion_es_de_un_solo_uso(client):
    client.get("/")
    _run_until_owner(client)
    first = client.post("/replay/voice", data={"typed": "sí, rota el token de bodega"})
    assert first.json()["status"] == "approved"
    again = client.post("/replay/voice", data={"typed": "sí, rota el token de bodega"})
    assert again.status_code == 200 and again.json()["status"] == "not_pending"
    # El resultado guardado sigue siendo el de la aprobación real.
    assert client.get("/replay/state").json()["voice"]["status"] == "approved"


def test_reset_y_cambio_de_escena(client):
    client.get("/")
    client.post("/replay/step/invoice")
    assert client.post("/replay/reset").json()["results"] == {}
    client.get("/?scene=frio")
    assert client.get("/replay/state").json()["scene"] == "frio"


def test_origen_cruzado_se_rechaza(client):
    client.get("/")
    r = client.post("/replay/step/invoice", headers={"origin": "https://otro.example"})
    assert r.status_code == 403


def test_sin_replay_home_la_raiz_sigue_siendo_el_panel(monkeypatch):
    monkeypatch.setenv("DEMO", "replay")
    monkeypatch.setenv("SHIELD_PANEL_SESSIONS", "1")
    monkeypatch.delenv("SHIELD_REPLAY_HOME", raising=False)
    c = TestClient(create_panel_app())
    assert "sphereCanvas" not in c.get("/").text
    assert c.get("/replay/state").status_code == 404
