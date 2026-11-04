"""El 409 «chain not started» del modo en vivo: arranque concurrente y pasos tempranos."""

from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient


class _SlowChain:
    started = 0

    def __init__(self) -> None:
        type(self).started += 1
        self.run_id = f"fake_{type(self).started}"
        self.total_cost_usd = 0.0
        self.vault = None
        self.results: dict = {}

    @classmethod
    def start(cls, *a, **k):  # como LiveChain.start: tarda (en Cloud Run fueron 3,56 s)
        time.sleep(0.4)
        return cls()

    def state(self) -> dict:
        return {"run_id": self.run_id, "status": "ready", "results": self.results}

    def step_invoice(self) -> dict:
        self.results["invoice"] = {"status": "ok"}
        return {"status": "ok", "run_id": self.run_id}


def _client(monkeypatch) -> TestClient:
    import web.live_chain as lc
    from web.app import create_panel_app

    monkeypatch.setenv("DEMO", "live")
    monkeypatch.delenv("SHIELD_LIVE_REMOTE", raising=False)
    monkeypatch.delenv("SHIELD_PANEL_SESSIONS", raising=False)
    _SlowChain.started = 0
    monkeypatch.setattr(lc, "LiveChain", _SlowChain)
    return TestClient(create_panel_app())


def test_concurrent_start_builds_one_chain(monkeypatch):
    client = _client(monkeypatch)
    out: list[str] = []
    ts = [
        threading.Thread(target=lambda: out.append(client.post("/live/start").json()["run_id"]))
        for _ in range(3)
    ]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert _SlowChain.started == 1, f"se armaron {_SlowChain.started} cadenas"
    assert len(set(out)) == 1


def test_step_during_start_waits_instead_of_409(monkeypatch):
    client = _client(monkeypatch)
    t = threading.Thread(target=lambda: client.post("/live/start"))
    t.start()
    time.sleep(0.05)  # el primer paso llega mientras /live/start sigue armando la cadena
    r = client.post("/live/step/invoice")
    t.join()
    assert r.status_code == 200, r.text
    assert _SlowChain.started == 1


def test_later_step_without_chain_409_carries_status_error(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/live/step/count")
    assert r.status_code == 409
    assert r.json()["status"] == "error"  # runUntilOwner corta con status == "error"
    assert _SlowChain.started == 0  # un paso intermedio no arma una cadena nueva


def test_invoice_on_instance_without_chain_starts_it(monkeypatch):
    # Cloud Run 3-nov: /live/start lo atendió una instancia y los pasos otra.
    client = _client(monkeypatch)
    r = client.post("/live/step/invoice")
    assert r.status_code == 200, r.text
    assert _SlowChain.started == 1
    assert client.get("/live/state").json()["results"] == {"invoice": {"status": "ok"}}


def test_live_page_js_waits_for_start_and_stops_on_http_error():
    from web.live_page import render_live_page

    html = render_live_page("en")
    loop = html.split("async function runUntilOwner()")[1][:400]
    assert "await ensureStarted()" in loop
    step = html.split("async function runStep(step)")[1][:1600]
    assert "await ensureStarted();" in step
    assert 'if (!res.ok && !data.status) data.status = "error";' in step
