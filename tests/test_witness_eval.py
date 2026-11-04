"""Harness del eval del testigo con cuadros sintéticos y SAM falso (sin red)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from evals.witness.run_witness_eval import (
    load_labels,
    parse_frame_name,
    percentile,
    run_eval,
    source_for,
)


def _write_frame(path: Path) -> None:
    buf = io.BytesIO()
    Image.new("RGB", (120, 80), (10, 200, 10)).save(buf, format="JPEG")
    path.write_bytes(buf.getvalue())


def _box(i: int) -> str:
    return f"{i}<|box;x1=10;y1=10;x2=30;y2=60;w=120;h=80|><|mask;x=0;y=0;data=2,2,~ab|>"


def test_parse_frame_name_and_percentile():
    cam, ts = parse_frame_name("cocina1_20261104-201500.jpg")
    assert cam == "cocina1" and ts.startswith("2026-11-04T20:15:00")
    assert parse_frame_name("raro.jpg") == ("raro", "")
    assert parse_frame_name("cocina1-noche-0300_20261104-204645.jpg")[0] == "cocina1-noche-0300"
    assert source_for("cocina1-noche-0300_20261104-204645.jpg") == "playback"
    assert percentile([], 50) is None
    assert percentile([1, 2, 3, 4], 50) == 2 and percentile([1, 2, 3, 4], 95) == 4


def test_run_eval_metrics_and_no_private_paths(tmp_path):
    frames = tmp_path / "privado"
    frames.mkdir()
    for name in ("cocina1_20261104-201500.jpg", "sala_20261104-201600.jpg"):
        _write_frame(frames / name)
    labels = {
        "cocina1_20261104-201500.jpg": {"people": 2, "door_open": True},
        "sala_20261104-201600.jpg": {"people": 0, "door_open": None},
        "falta_20261104-201700.jpg": {"people": 1, "door_open": False},
    }
    outputs = {"person": "<0f>" + _box(0) + _box(1), "open doorway": "<0f>" + _box(0),
               "closed door": ""}
    report = run_eval(frames, labels, sam_fn=lambda c, m: outputs.get(c, ""),
                      redact_out=tmp_path / "revision")
    s = report["summary"]
    assert s["frames"] == 2 and s["sam_errors"] == 0
    assert s["people_exact"] == 1 and s["people_mae"] == 1.0
    assert s["door_labeled"] == 1 and s["door_correct"] == 1
    assert s["cost_usd_total"] == pytest.approx(2 * 3 * 0.0025)
    assert s["count"]["within_1"] == 1 and s["count_by_camera"]["sala"]["mae"] == 2.0
    assert s["presence"] == {"n": 2, "tp": 1, "fp": 1, "fn": 0, "tn": 0, "precision": 0.5,
                             "recall": 1.0, "accuracy": 0.5, "empty_precision": None,
                             "empty_recall": 0.0}
    assert report["meta"]["labeled_frames_missing"] == ["falta_20261104-201700.jpg"]
    dumped = json.dumps(report)
    assert str(tmp_path) not in dumped and "/" not in "".join(
        r["frame"] for r in report["frames"])
    assert "x1" not in dumped and "person_boxes" not in dumped  # sin cajas
    written = sorted(p.name for p in (tmp_path / "revision").iterdir())
    assert written == ["cocina1_20261104-201500.redacted.jpg", "observations.json",
                       "sala_20261104-201600.redacted.jpg"]
    obs = json.loads((tmp_path / "revision" / "observations.json").read_text())
    assert [o["source"] for o in obs] == ["live_capture", "live_capture"]
    assert all("redacted_image" not in o for o in obs)


def test_redact_out_inside_repo_is_refused(tmp_path):
    repo_dir = Path(__file__).resolve().parents[1] / "evals" / "recorded" / "nope"
    with pytest.raises(SystemExit):
        run_eval(tmp_path, {}, sam_fn=lambda c, m: "", redact_out=repo_dir)
    assert not repo_dir.exists()


def test_labels_file_ignores_comment_keys():
    path = Path(__file__).resolve().parents[1] / "evals" / "witness" / "labels.json"
    assert all(not k.startswith("_") for k in load_labels(path))
