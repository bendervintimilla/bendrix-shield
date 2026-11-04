"""Aplicaciones de vigilancia del testigo: offline, cuadros sintéticos, modelos falsos."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from evals.witness.run_surveillance import base_camera, frame_info, run
from shield.autopilot import detect
from shield.witness import WitnessObservation
from shield.witness.surveillance import (
    OpeningHours,
    after_hours_check,
    alert_event,
    choose_stock_concept,
    occupancy,
    playback_time,
    shift_log,
    stock_watch,
    template_log,
    unattended_cash_desk,
    validate_log,
)

H = OpeningHours.parse("12:00-00:30", "Europe/Madrid")


def _obs(people: int, at: str, *, camera: str = "cocina1", ok: bool = True,
         img: bytes | None = None, source: str = "live_capture") -> WitnessObservation:
    return WitnessObservation(camera=camera, site="madrid", room=camera, captured_at=at,
                              people=people, door_open=None, source=source,
                              redacted_image=img, error=None if ok else "boom")


def test_opening_hours_overnight():
    assert H.is_open(datetime.fromisoformat("2026-11-04T20:00:00+01:00"))
    assert H.is_open(datetime.fromisoformat("2026-11-05T00:15:00+01:00"))
    assert not H.is_open(datetime.fromisoformat("2026-11-05T03:00:00+01:00"))
    assert not H.is_open(datetime.fromisoformat("2026-11-04T11:59:00+01:00"))
    assert not H.is_open(datetime(2026, 11, 4, 2, 0, tzinfo=UTC))  # 03:00 Madrid
    day = OpeningHours.parse("09:00-17:00")
    assert day.is_open(datetime.fromisoformat("2026-11-04T10:00:00+01:00"))


def test_after_hours_rules_and_autopilot_event():
    night = "2026-11-04T03:00:00+01:00"
    assert after_hours_check(_obs(0, night), H).kind == "after_hours_all_clear"
    hit = after_hours_check(_obs(2, night), H)
    assert (hit.kind, hit.severity) == ("after_hours_presence", "high")
    assert after_hours_check(_obs(3, "2026-11-04T20:00:00+01:00"), H).severity == "info"
    assert after_hours_check(_obs(0, night, ok=False), H).severity == "medium"
    ev = alert_event(hit)
    assert ev.app == "camera" and ev.values["alert_severity"] == "high"
    kinds = {f.kind: f.severity for f in detect([ev])}
    assert kinds["after_hours_presence"] == "high"
    assert detect([alert_event(after_hours_check(_obs(0, night), H))]) == []


def test_choose_stock_concept_grouped_scenes():
    pick = choose_stock_concept({"cardboard box": {"night": [12, 12], "live": [6, 7]},
                                 "box": {"night": [2, 9], "live": [9, 3]}})
    assert pick["chosen"] == "cardboard box"


def test_choose_stock_concept_by_data():
    pick = choose_stock_concept({"cardboard box": [10, 11, 10], "box": [14, 7, 20],
                                 "crate": [0, 0, 0]})
    assert pick["chosen"] == "cardboard box" and pick["table"]["crate"]["mean"] == 0
    assert pick["table"]["cardboard box"]["cv_within_scene"] is not None
    assert "variación" in pick["why"]
    assert choose_stock_concept({"box": [0, 0]})["chosen"] is None


def test_stock_watch_thresholds():
    kw = {"camera": "almacen", "room": "almacen", "hours": H, "drop_threshold": 0.3}
    assert stock_watch(10, 5, at="2026-11-04T03:00:00+01:00", **kw).severity == "high"
    assert stock_watch(10, 5, at="2026-11-04T20:00:00+01:00", **kw).kind == \
        "stock_drop_open_hours"
    assert stock_watch(10, 8, at="2026-11-04T03:00:00+01:00", **kw).kind == "stock_ok"
    assert stock_watch(0, 0, at="2026-11-04T03:00:00+01:00", **kw).kind == "stock_no_reference"


def test_unattended_cash_desk():
    at = "2026-11-04T20:00:00+01:00"
    pos = {"action": "drawer_open", "ts": "2026-11-04T20:00:05+01:00", "simulated": True}
    a = unattended_cash_desk(_obs(0, at, camera="caja1"), pos)
    assert (a.kind, a.severity, a.simulated) == ("drawer_open_unattended", "high", True)
    assert unattended_cash_desk(_obs(1, at, camera="caja1"), pos).severity == "info"
    assert unattended_cash_desk(None, pos).kind == "drawer_open_unverified"
    old = _obs(1, "2026-11-04T19:00:00+01:00", camera="caja1")
    assert unattended_cash_desk(old, pos).kind == "drawer_open_unverified"
    assert "simulado" in detect([alert_event(a)])[0].reason


FACTS = {"opening_hours": "12:00-00:30 Europe/Madrid",
         "occupancy": {"cocina1": {"people_latest": 2}, "almacen": {"people_latest": 0}},
         "alerts_by_kind": {"after_hours_presence": 1}, "high_alerts": 3}


def test_validate_log_numbers_and_people_descriptions():
    good = ["Kitchen 1: 2 people.", "Storage: 0 people.", "High alerts: 3.",
            "After-hours presence: 1.", "Hours 12:00-00:30."]
    assert validate_log(good, good, FACTS) == []
    bad = good[:4] + ["7 boxes moved by a man wearing a red shirt."]
    problems = validate_log(bad, good, FACTS)
    assert any("'7'" in p for p in problems) and any("describe personas" in p for p in problems)
    assert any("líneas" in p for p in validate_log(good[:3], good, FACTS))


def test_template_log_is_valid():
    en, es = template_log(FACTS)
    assert validate_log(en, es, FACTS) == []


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1600, 900), (90, 90, 90)).save(buf, format="JPEG")
    return buf.getvalue()


def test_shift_log_sends_only_redacted_downscaled_images_and_retries():
    sent: list = []
    lines = ["Kitchen 1: 2 people.", "Storage: 0 people.", "High alerts: 3.",
             "After-hours presence: 1.", "No other events."]
    replies = iter([
        (json.dumps({"en": lines[:4] + ["99 boxes."], "es": lines}), "resp_1", 0.01),
        (json.dumps({"en": lines, "es": lines}), "resp_2", 0.01),
    ])

    def spark(messages):
        sent.append(messages)
        return next(replies)

    obs = [_obs(2, "2026-11-04T20:00:00+01:00", img=_jpeg()), _obs(0, "2026-11-04T20:00:00+01:00")]
    log = shift_log(obs, FACTS, spark_fn=spark)
    assert log.valid and log.source == "muse-spark-1.3" and log.attempts == 2
    assert log.response_ids == ["resp_1", "resp_2"] and log.cost_usd == pytest.approx(0.02)
    content = sent[1][0]["content"]
    imgs = [c for c in content if c["type"] == "image_url"]
    assert len(imgs) == 1 and log.images_sent == 1  # la obs sin imagen redactada no envía nada
    import base64
    data = base64.b64decode(imgs[0]["image_url"]["url"].split(",", 1)[1])
    assert max(Image.open(io.BytesIO(data)).size) <= 768
    assert "rejected" in content[0]["text"]


def test_shift_log_falls_back_to_template():
    log = shift_log([], FACTS, spark_fn=lambda m: ("no json", "r", 0.0))
    assert log.source == "template" and log.valid and log.problems
    boom = shift_log([], FACTS, spark_fn=lambda m: (_ for _ in ()).throw(RuntimeError("x")))
    assert boom.source == "template" and "spark error" in boom.problems[0]


def test_frame_naming_and_playback_time():
    assert base_camera("almacen_noche-0300") == "almacen"
    assert base_camera("cocina1-noche-0300") == "cocina1"
    info = frame_info("almacen_noche-0300_20261104-204645.jpg")
    assert info["camera"] == "almacen" and info["source"] == "playback"
    assert "T03:00:00" in info["captured_at"]
    assert playback_time("x", "2026-11-04T20:00:00+01:00") is None
    assert frame_info("caja1_20261104-204645.jpg")["source"] == "live_capture"


def test_occupancy_latest_valid_per_camera():
    occ = occupancy([_obs(1, "2026-11-04T20:00:00+01:00"),
                     _obs(3, "2026-11-04T20:01:00+01:00"),
                     _obs(9, "2026-11-04T20:02:00+01:00", ok=False)])
    assert occ["cocina1"]["people"] == 3


def _box(i: int) -> str:
    return f"{i}<|box;x1=10;y1=10;x2=30;y2=60;w=120;h=80|><|mask;x=0;y=0;data=2,2,~ab|>"


def test_runner_end_to_end_offline(tmp_path):
    frames = tmp_path / "privado"
    frames.mkdir()
    names = ["caja1_20261104-212200.jpg", "caja1_noche-0300_20261104-212500.jpg",
             "almacen_20261104-212300.jpg", "almacen_20261104-212302.jpg",
             "almacen_noche-0300_20261104-212600.jpg", "almacen_noche-0300_20261104-212602.jpg",
             "nota.txt"]
    for n in names:
        (frames / n).write_bytes(_jpeg() if n.endswith(".jpg") else b"x")
    night_jpeg = (frames / "almacen_noche-0300_20261104-212600.jpg").read_bytes()
    live_caja = (frames / "caja1_20261104-212200.jpg").read_bytes()
    # Distinguir cuadros: la noche tiene más cajas; la caja en vivo tiene gente.
    buf = io.BytesIO()
    Image.new("RGB", (1600, 900), (200, 30, 30)).save(buf, format="JPEG")
    live_caja = buf.getvalue()
    (frames / "caja1_20261104-212200.jpg").write_bytes(live_caja)
    buf = io.BytesIO()
    Image.new("RGB", (1600, 900), (10, 90, 90)).save(buf, format="JPEG")
    night_jpeg = buf.getvalue()
    for n in names:
        if n.startswith("almacen_noche"):
            (frames / n).write_bytes(night_jpeg)
    import base64 as b64
    night_url = "data:image/jpeg;base64," + b64.b64encode(night_jpeg).decode()
    caja_url = "data:image/jpeg;base64," + b64.b64encode(live_caja).decode()

    def sam(concept, media):
        night = media["url"] == night_url
        if concept == "person":
            return "<0f>" + _box(0) + _box(1) if media["url"] == caja_url else ""
        n = {"cardboard box": 12 if night else 6, "box": 9, "crate": 0}[concept]
        if concept == "box" and night:
            n = 2  # 'box' no ve el apilado: mucha variación entre escenas -> se descarta
        return "<0f>" + "".join(_box(i) for i in range(n))

    report = {"en": {"bullets": ["Cash desk at 03:00: drawer opened 1 time with nobody there "
                                 "(simulated test).",
                                 "Storeroom: 12 boxes at 03:00, 6 now, expected.",
                                 "After hours: nobody on site.",
                                 "Live now: Cash desk staff present."],
                     "action": "Check the cash desk recording from 03:00."},
              "es": {"bullets": ["Caja a las 03:00: cajón abierto 1 vez sin nadie (prueba "
                                 "simulada).",
                                 "Almacén: 12 cajas a las 03:00, 6 ahora, esperado.",
                                 "Fuera de horario: nadie en el local.",
                                 "Ahora: Caja con personal."],
                     "action": "Revisa la grabación de la Caja de las 03:00."}}
    out = run(frames, tmp_path / "redactadas", hours=H, sam_fn=sam,
              spark_fn=lambda m: (json.dumps(report), "resp_x", 0.0),
              verified_empty=("caja1_noche", "almacen_noche"))
    pub = out["public"]
    for key in ("stock_watch", "cash_desk", "security_log", "after_hours"):
        card = pub[key]
        assert card["status"] in ("alert", "all_clear", "expected", "pending")
        for f in ("summary", "summary_es", "metric", "image", "model", "response_ids",
                  "latency_ms", "cost_usd"):
            assert f in card, (key, f)
        assert card["image"] is None or "/" not in card["image"]
    assert pub["stock_watch"]["status"] == "expected" and "12 → 6" in pub["stock_watch"]["metric"]
    assert pub["cash_desk"]["status"] == "alert"
    assert pub["cash_desk"]["image"] == "caja1_noche-0300_20261104-212500.redacted.jpg"
    log_text = pub["security_log"]["text"]["en"]
    assert log_text[0].startswith("Night & shift security report")
    assert log_text[-1].startswith("Action needed:")
    assert pub["security_log"]["model"] == "muse-spark-1.3", pub["security_log_detail"]
    facts = pub["security_log_detail"]["facts"]
    assert facts[0].startswith("Cash desk at 03:00: 0 people") and "simulated" in facts[0]
    assert any(f.startswith("Storeroom: 12 boxes at 03:00, 6 at") for f in facts)
    assert pub["after_hours"]["status"] == "all_clear"
    obs = out["private"]["observations"]
    assert all("recorded_at" in o for o in obs)
    st = pub["stock_detail"]
    assert st["concept_choice"]["chosen"] in ("cardboard box", "box")
    assert st["reference_median"] == 12 and st["current_median"] == 6
    assert st["measured_difference"] == -6
    assert st["actual"]["kind"] == "stock_drop_open_hours" and st["actual"]["severity"] == "low"
    cf = st["counterfactual_after_hours"]
    assert cf["kind"] == "stock_drop_after_hours" and cf["severity"] == "high"
    assert cf["autopilot_findings"][0]["kind"] == "stock_drop_after_hours"
    kinds = pub["alerts_by_kind"]
    assert kinds["drawer_open_unattended"] == 1 and kinds["drawer_open_attended"] == 1
    assert kinds["after_hours_all_clear"] == 3
    assert "stock_drop_after_hours" not in kinds  # en horario: sin alerta real
    assert pub["autopilot"]["incident_severity"] in ("high", "critical")
    assert pub["verified_empty"] == {"frames": 3, "written": 3, "withheld": 0}
    dumped = json.dumps(pub)
    assert str(tmp_path) not in dumped and "x1" not in dumped
    written = {p.name for p in (tmp_path / "redactadas").iterdir()}
    assert "almacen_20261104-212300.redacted.jpg" in written
    assert "caja1_noche-0300_20261104-212500.verified-empty.jpg" in written
    ve = json.loads((tmp_path / "redactadas" / "verified-empty.json").read_text())
    assert all(v["sam_people"] == 0 and v["sha256"] for v in ve)
    clean = Image.open(tmp_path / "redactadas" / "caja1_noche-0300_20261104-212500"
                       ".verified-empty.jpg")
    assert not clean.info.get("exif")
    with pytest.raises(SystemExit):
        run(frames, Path(__file__).resolve().parents[1] / "evals" / "nope", hours=H, sam_fn=sam)


REPORT_FACTS = ["Cash desk at 03:00: 0 people on camera while the POS reported 6 drawer "
                "openings (simulated test events) - needs review.",
                "Storeroom: 18 boxes at 03:00, 12 at 20:57, during opening hours - expected.",
                "After hours (00:30-12:00): 22 camera checks across 3 cameras, nobody on site.",
                "Live now: Kitchen 1 one person, Hallway several people."]


def _report(first="Cash desk: drawer opened 6 times at 03:00 with nobody there (simulated).",
            n=4, action="Check the cash desk recording from 03:00."):
    bullets = [first, "Storeroom: 18 boxes at 03:00, 12 at 20:57, expected.",
               "After hours: nobody on site.", "Live now: kitchens and hallway busy.",
               "Nothing else to report."][:n]
    es = ["Caja: cajón abierto 6 veces a las 03:00 sin nadie (simulado).",
          "Almacén: 18 cajas a las 03:00, 12 a las 20:57, esperado.",
          "Fuera de horario: nadie en el local.", "Ahora: cocinas y pasillo con actividad.",
          "Nada más."][:n]
    return {"en": {"bullets": bullets, "action": action},
            "es": {"bullets": es, "action": "Revisa la grabación de la Caja de las 03:00."}}


def test_shift_report_valid_composes_title_and_action():
    from shield.witness.surveillance import REPORT_TITLE_EN, REPORT_TITLE_ES, shift_report
    calls = []

    def spark(messages):
        calls.append(messages)
        return json.dumps(_report()), "chatcmpl-1", 0.004

    obs = [_obs(0, "2026-11-04T03:00:00+01:00", camera="caja1", img=_jpeg())]
    log = shift_report(obs, REPORT_FACTS, spark_fn=spark)
    assert log.valid and log.source == "muse-spark-1.3" and log.attempts == 1
    assert log.en[0] == REPORT_TITLE_EN and log.es[0] == REPORT_TITLE_ES
    assert log.en[-1] == "Action needed: Check the cash desk recording from 03:00."
    assert log.es[-1].startswith("Acción necesaria:")
    assert len(log.en) == 6 and log.response_ids == ["chatcmpl-1"]
    prompt = calls[0][0]["content"][0]["text"]
    assert "FACTS" in prompt and REPORT_FACTS[0] in prompt


@pytest.mark.parametrize("bad,why", [
    (_report(first="Storeroom first, 18 boxes."), "first bullet"),
    (_report(n=3), "bullets"),
    (_report(first="Cash desk: a man wearing a cap opened the drawer 6 times."), "personas"),
    (_report(first="Cash desk: drawer opened 9 times."), "'9'"),
    (_report(action=""), "missing action"),
])
def test_validate_report_rejects(bad, why):
    from shield.witness.surveillance import validate_report
    assert any(why in p for p in validate_report(bad, REPORT_FACTS)), why


def test_fast_spark_fn_falls_back_without_params():
    from shield.meta_client import CallResult
    from shield.witness.surveillance import make_meta_spark_fn
    seen = []

    class Client:
        def chat_completions(self, **kw):
            seen.append(sorted(kw))
            if "reasoning_effort" in kw:
                raise RuntimeError("Meta Model API HTTP 400: unsupported")
            return CallResult(data={"id": "c1", "choices": [{"message": {"content": "{}"}}]},
                              model="muse-spark-1.3", cost_usd=0.001)

    text, rid, cost = make_meta_spark_fn(Client())([{"role": "user", "content": "x"}])
    assert (text, rid) == ("{}", "c1") and len(seen) == 2
