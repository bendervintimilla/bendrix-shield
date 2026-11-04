"""Repetición pública: la pantalla de /live corriendo sobre grabaciones reales.

Cada visitante tiene su propia corrida (`ReplayRun`), en memoria y con caducidad.
Los pasos devuelven lo que quedó grabado de una corrida real (escena Bodega,
`evals/recorded/live-run-video-take-2026-11-02.json`) o del escenario determinista
de cadena de frío (`evals/recorded/cold-chain-replay.json`). No se llama a ningún
modelo, no hay llaves ni gasto, y `/live/*` sigue cerrado en este servicio.

Lo único que NO es grabado es la decisión del dueño: pasa por el mismo
`ApprovalBroker` + `VoiceApprovalFlow` del producto, con el nonce de esa solicitud,
así que la aprobación de un solo uso es la real.
"""

from __future__ import annotations

import copy
import json
import re
import secrets
import time
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from channels.approvals import ApprovalBroker
from channels.voice import VoiceApprovalFlow
from web.brand import BRAND, SUBTITLE

SCENES = ("bodega", "frio")
_RECORDED = Path(__file__).resolve().parents[1] / "evals" / "recorded"
_BODEGA_FILE = _RECORDED / "live-run-video-take-2026-11-02.json"
_COLD_FILE = _RECORDED / "cold-chain-replay.json"
FIXTURES = {"invoice": "invoice-poisoned.png", "shelf": "shelf-boxes.png"}

_STEP_ORDER = ("invoice", "count", "attack", "guardian", "voice", "contain", "revoke")
# Agente cuyo token robó el atacante y agentes con token en cada escena.
_SCENE_AGENTS = {
    "bodega": ("bodega", ("bodega", "compras", "guardian")),
    "frio": ("refrigeracion", ("refrigeracion", "bodega", "compras")),
}
_PROVENANCE_GROUP = {
    "invoice": "invoice",
    "spark_document_review": "invoice",
    "invoice_policy": "invoice",
    "forced_policy_test": "invoice",
    "count": "count",
    "attack": "attack",
    "guardian": "guardian",
    "contain": "contain",
}

_cache: dict[str, Any] = {}

_ADVISORIES = _RECORDED.parent / "advisories"
_CVE_PHONE = "CVE-[REDACTED:phone]"
_CVE_PHONE_TITLED = re.compile(re.escape(_CVE_PHONE) + r'(", "title": ")([^"]+)"')


def _fix_cve_redaction(node: Any) -> Any:
    """Deshace en la grabación el falso positivo «CVE-[REDACTED:phone]».

    El patrón de teléfono viejo comía «2026-NNNN» de los CVE. Si la grabación
    trae el título del aviso (vuelta de ``list_advisories``), el id se recupera
    del mismo `evals/advisories/*.json` que sirvió la herramienta, solo si el
    título es único; si no, queda «CVE-(id)». No inventa ids.
    """
    if isinstance(node, dict):
        return {k: _fix_cve_redaction(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_fix_cve_redaction(v) for v in node]
    if not isinstance(node, str) or _CVE_PHONE not in node:
        return node
    by_title: dict[str, list[str]] = {}
    for f in sorted(_ADVISORIES.glob("*.json")):
        try:
            adv = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(adv, dict) and str(adv.get("id", "")).startswith("CVE-"):
            by_title.setdefault(str(adv.get("title", "")), []).append(str(adv["id"]))

    def _sub(m: re.Match[str]) -> str:
        ids = by_title.get(m.group(2), [])
        return (ids[0] if len(ids) == 1 else "CVE-(id)") + m.group(1) + m.group(2) + '"'

    return _CVE_PHONE_TITLED.sub(_sub, node).replace(_CVE_PHONE, "CVE-(id)")


def _load(path: Path) -> dict[str, Any]:
    key = str(path)
    if key not in _cache:
        _cache[key] = _fix_cve_redaction(json.loads(path.read_text(encoding="utf-8")))
    return copy.deepcopy(_cache[key])


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ReplayRun:
    """Una corrida de repetición de un visitante."""

    def __init__(self, scene: str = "bodega") -> None:
        self.lock = Lock()
        self.scene = scene if scene in SCENES else "bodega"
        self._reset()

    # -- ciclo de vida -----------------------------------------------------------
    def _reset(self) -> None:
        self.run_id = "replay_" + secrets.token_hex(6)
        # El reloj «Chain duration» arranca con el primer paso, no al abrir la página.
        self.started: float | None = None
        self.started_at: str | None = None
        self.results: dict[str, Any] = {}
        self.done: list[str] = []
        self.broker = ApprovalBroker()
        self.flow = VoiceApprovalFlow(self.broker)
        self.approval_id: str | None = None
        self.attack_started_at: str | None = None
        self.contained_in_s: float | None = None
        self.plan: dict[str, Any] | None = None
        self._recorded = _load(_BODEGA_FILE) if self.scene == "bodega" else _load(_COLD_FILE)

    def reset(self, scene: str | None = None) -> dict[str, Any]:
        if scene in SCENES:
            self.scene = scene  # type: ignore[assignment]
        self._reset()
        return self.state()

    # -- estado ------------------------------------------------------------------
    def _provenance(self) -> list[dict[str, Any]]:
        if self.scene != "bodega":
            return []
        rows = []
        for row in self._recorded.get("provenance", []):
            group = _PROVENANCE_GROUP.get(str(row.get("step")))
            if group and group in self.done:
                rows.append(row)
        return rows

    def state(self) -> dict[str, Any]:
        voice = self.results.get("voice") if isinstance(self.results.get("voice"), dict) else {}
        return {
            "run_id": self.run_id,
            "status": "ready",
            "replay": True,
            "scene": self.scene,
            "started_at": self.started_at,
            "duration_s": (
                0.0 if self.started is None else round(time.monotonic() - self.started, 3)
            ),
            "cap_usd": 0.0,
            "total_cost_usd": 0.0,
            "gateway_logged_cost_usd": 0.0,
            "material_label": self._recorded.get("material_label", ""),
            "brand": BRAND,
            "subtitle": SUBTITLE,
            "results": self.results,
            "anomalies": (self.results.get("attack") or {}).get("anomalies", []),
            "approval_id": self.approval_id,
            "plan": self.plan,
            "contained_in_s": self.contained_in_s,
            "provenance": self._provenance(),
            "voice": {
                "channel": "browser" if voice else None,
                "input_mode": "typed" if voice else None,
                "transcript": voice.get("transcript", ""),
                "status": voice.get("status"),
                "intent": voice.get("intent"),
            },
        }

    # -- pasos -------------------------------------------------------------------
    def _error(
        self, message: str, *, need: str | None = None, code: str | None = None
    ) -> dict[str, Any]:
        """Error de paso. ``need`` es el paso que falta: la pantalla lo traduce."""
        out: dict[str, Any] = {"status": "error", "error": message}
        if code:
            out["error_code"] = code
        if need:
            out["error_code"] = "needs_step"
            out["need"] = need
        return out

    def step(self, name: str) -> dict[str, Any]:
        if name not in _STEP_ORDER or name == "voice":
            return self._error(f"unknown replay step: {name}")
        needs = {"guardian": "attack", "contain": "voice", "revoke": "attack"}
        need = needs.get(name)
        if need and need not in self.done:
            return self._error(f"first run: {need}", need=need)
        if name in ("attack", "guardian") and "contain" in self.done:
            # Ya contenido: repetir el ataque crearía otra aprobación con la corrida cerrada.
            return self._error("this run is already contained: start a new run", code="contained")
        if name == "contain" and (self.results.get("voice") or {}).get("status") != "approved":
            return {
                "status": "not_approved",
                "error": "the owner has not approved yet",
                "error_code": "not_approved",
            }
        if self.started is None:
            self.started = time.monotonic()
            self.started_at = _now_iso()
        if name == "revoke":
            builder = self._revoke
        else:
            builder = getattr(self, f"_{self.scene}_{name}")
        out = builder()
        self.results[name] = out
        if name not in self.done:
            self.done.append(name)
        return out

    # ---- g · emergencia: no es grabado, corre el gateway real en memoria ----
    def _revoke(self) -> dict[str, Any]:
        """Revoca todo con el endpoint real `/shield/revoke-all` sobre un registro propio.

        Cada visitante tiene su gateway y su registro en memoria; el upstream es falso y
        no se alcanza (el token revocado da 401 antes). Sin llaves ni gasto.
        """
        import httpx
        from fastapi.testclient import TestClient

        from shield.gateway.app import create_app
        from shield.registry import Registry
        from shield.vault.vault import MemoryVault
        from web.emergency import run_emergency_revoke

        stolen, agents = _SCENE_AGENTS[self.scene]
        registry = Registry(":memory:")
        raw: dict[str, str] = {}
        ids: dict[str, str] = {}
        for agent in agents:
            token, value = registry.create_token(agent, "crew", models=["muse-spark-1.3"])
            raw[agent], ids[agent] = value, token.token_id
        probes = [("attacker", raw[stolen])]
        if "contain" in self.done:
            # Como en la corrida: el token robado ya se rotó con la voz del dueño.
            rotated = registry.rotate(ids[stolen])
            if rotated is not None:
                raw[stolen] = rotated[1]
        probes += [(agent, raw[agent]) for agent in agents]

        def _no_upstream(request: httpx.Request) -> httpx.Response:
            return httpx.Response(599, json={"error": "upstream disabled in replay"})

        key = secrets.token_urlsafe(32)
        app = create_app(
            registry=registry,
            vault=MemoryVault({}),
            upstream_transport=httpx.MockTransport(_no_upstream),
            sandbox=True,
            emergency_token=key,
        )
        try:
            with TestClient(app) as client:
                out = run_emergency_revoke(client, key, probes, registry=registry)
        finally:
            registry.close()
        out["kind"] = "emergency_revoke"
        return out

    # ---- escena Bodega (corrida real grabada) ----
    def _bodega_invoice(self) -> dict[str, Any]:
        return self._recorded["results"]["invoice"]

    def _bodega_count(self) -> dict[str, Any]:
        return self._recorded["results"]["count"]

    def _bodega_attack(self) -> dict[str, Any]:
        out = self._recorded["results"]["attack"]
        self.attack_started_at = _now_iso()
        out["attack_started_at"] = self.attack_started_at
        return out

    def _bodega_guardian(self) -> dict[str, Any]:
        out = self._recorded["results"]["guardian"]
        plan = out["plan"]
        self.plan = plan
        req = self.broker.request(
            {
                "summary": plan.get("summary", ""),
                "steps": [
                    {**s, "requires_approval": s.get("action") != "verify"}
                    for s in plan.get("steps", [])
                ],
            }
        )
        self.approval_id = req.approval_id
        out["approval_id"] = req.approval_id
        return out

    def _bodega_contain(self) -> dict[str, Any]:
        out = self._recorded["results"]["contain"]
        out["approval_id"] = self.approval_id
        out["attack_started_at"] = self.attack_started_at
        # «Real time to first 401» es el de este visitante (como en frío); el tiempo de la
        # corrida en vivo grabada se muestra aparte, sin hacerlo pasar por el del visitante.
        out["recorded_contained_in_s"] = out.get("contained_in_s")
        started = datetime.fromisoformat(self.attack_started_at or _now_iso())
        elapsed = round((datetime.now(UTC) - started).total_seconds(), 3)
        out["contained_in_s"] = elapsed
        self.contained_in_s = elapsed
        return out

    # ---- escena Cadena de frío (escenario determinista grabado) ----
    def _cold_step(self, name: str) -> dict[str, Any]:
        for st in self._recorded["steps"]:
            if st["step"] == name:
                return st
        raise KeyError(name)

    def _frio_invoice(self) -> dict[str, Any]:
        st = self._cold_step("legit_setpoint")
        return {"status": "ok", "kind": "cold_legit", **st}

    def _frio_count(self) -> dict[str, Any]:
        st = self._cold_step("foreign_token_scope")
        return {"status": "ok", "kind": "cold_scope", **st}

    def _frio_attack(self) -> dict[str, Any]:
        st = self._cold_step("stolen_token_attack")
        self.attack_started_at = _now_iso()
        reasons = self._recorded.get("attack_reasons", [])
        kinds = [r.split(":", 1)[0] for r in reasons]
        return {
            "status": "ok",
            "kind": "cold_attack",
            "statuses": [st["gateway_status_before_rotation"]] * len(st["attacks"]),
            "attacks": st["attacks"],
            "anomalies": [
                {"agent": "refrigeracion", "kind": k, "detail": r, "severity": "high", "count": 1}
                for k, r in zip(kinds, reasons, strict=False)
            ],
            "attack_started_at": self.attack_started_at,
        }

    def _frio_guardian(self) -> dict[str, Any]:
        plan = {
            "summary": "Rotar solo el token de Refrigeración; Bodega y Compras no se tocan.",
            "reasoning": (
                "El token de Refrigeración intentó subir la cámara a 50 °C y el congelador a "
                "5 °C a las 03:00 desde BR (esperado EC): fuera de rango, fuera de horario y "
                "origen inesperado. Rotarlo corta al atacante sin parar la cocina."
            ),
            "exposures": [],
            "steps": [
                {
                    "action": "rotate_token",
                    "target": "refrigeracion",
                    "reason": "token usado fuera de rango, de horario y de origen",
                    "requires_approval": True,
                }
            ],
        }
        # Mismo plan en inglés para la pantalla en EN (la escena es determinista, sin modelo).
        plan_en = {
            "summary": (
                "Rotate only the Refrigeration token; Warehouse and Purchasing are untouched."
            ),
            "reasoning": (
                "The Refrigeration token tried to set the cold room to 50 °C and the freezer to "
                "5 °C at 03:00 from BR (expected EC): out of range, off hours and from an "
                "unexpected origin. Rotating it locks the attacker out without stopping the "
                "kitchen."
            ),
            "exposures": [],
            "steps": [
                {
                    "action": "rotate_token",
                    "target": "refrigeracion",
                    "reason": "token used out of range, off hours and from an unexpected origin",
                    "requires_approval": True,
                }
            ],
        }
        self.plan = plan
        req = self.broker.request(plan)
        self.approval_id = req.approval_id
        return {
            "status": "ok",
            "kind": "cold_plan_deterministic",
            "plan": plan,
            "plan_en": plan_en,
            "approval_id": req.approval_id,
            "turns": [],
        }

    def _frio_contain(self) -> dict[str, Any]:
        after = self._cold_step("after_rotation")
        rotation = self._cold_step("owner_voice_rotation")
        # Tiempo medido por el visitante, desde que el atacante entró hasta el primer 401.
        started = datetime.fromisoformat(self.attack_started_at or _now_iso())
        elapsed = round((datetime.now(UTC) - started).total_seconds(), 3)
        self.contained_in_s = elapsed
        return {
            "status": "ok",
            "kind": "cold_contain",
            "executed": [
                {
                    "action": "rotate_token",
                    "target": "refrigeracion",
                    "status": rotation["rotation_status"],
                }
            ],
            "approval_id": self.approval_id,
            "attacker_after": [after["attacker_status"]],
            "refrigeracion_status": after["refrigeracion_status"],
            "bodega_status": after["bodega_status"],
            "compras_status": after["compras_status"],
            "sdk_statuses": [],
            "contained_in_s": elapsed,
            "attack_started_at": self.attack_started_at,
        }

    # -- decisión del dueño (real, con nonce) ------------------------------------
    def voice(self, typed: str) -> dict[str, Any]:
        if not self.approval_id:
            return self._error("run the guardian first", need="guardian")
        text = (typed or "").strip()
        if not text:
            out = {"status": "no_speech", "transcript": "", "intent": {}}
            self.results["voice"] = out
            return out
        req = self.broker.get(self.approval_id)
        if req is not None and req.status != "pending":
            # Una aprobación se decide una sola vez: repetir la orden no hace nada.
            out = {
                "status": "not_pending",
                "transcript": text,
                "intent": (self.results.get("voice") or {}).get("intent") or {},
                "approval_id": self.approval_id,
                "channel": "browser",
                "input_mode": "typed",
            }
            return out
        outcome = self.flow.handle_transcript(
            self.approval_id, text, nonce=req.nonce if req else None
        )
        out = {
            "status": outcome.get("status"),
            "transcript": text,
            "input_mode": "typed",
            "intent": outcome.get("intent"),
            "approval_id": self.approval_id,
            "channel": "browser",
        }
        for key in ("approved_steps", "will_run", "excluded", "unmatched", "reason"):
            if key in outcome:
                out[key] = outcome[key]
        self.results["voice"] = out
        if out["status"] == "approved" and "voice" not in self.done:
            self.done.append("voice")
        return out

    def voice_confirm(self) -> dict[str, Any]:
        if not self.approval_id:
            return self._error("no pending approval", need="guardian")
        req = self.broker.get(self.approval_id)
        outcome = self.flow.confirm(self.approval_id, nonce=req.nonce if req else None)
        prev = self.results.get("voice") or {}
        out = {**prev, "status": outcome.get("status")}
        if "approved_steps" in outcome:
            out["approved_steps"] = outcome["approved_steps"]
        self.results["voice"] = out
        if out["status"] == "approved" and "voice" not in self.done:
            self.done.append("voice")
        return out

    def voice_cancel(self) -> dict[str, Any]:
        if not self.approval_id:
            return self._error("no pending approval", need="guardian")
        outcome = self.flow.cancel(self.approval_id)
        prev = self.results.get("voice") or {}
        out = {**prev, "status": outcome.get("status")}
        self.results["voice"] = out
        return out

    def export(self) -> str:
        return json.dumps(
            {
                "run_id": self.run_id,
                "scene": self.scene,
                "replay": True,
                "source": "evals/recorded/"
                + (_BODEGA_FILE.name if self.scene == "bodega" else _COLD_FILE.name),
                "provenance": self._provenance(),
            },
            ensure_ascii=False,
            indent=2,
        )


class ReplayStore:
    """Corridas de repetición por visitante: en memoria, con tope y caducidad."""

    def __init__(self, *, max_sessions: int = 200, ttl_s: float = 1800.0) -> None:
        self.max_sessions = max_sessions
        self.ttl_s = ttl_s
        self._items: OrderedDict[str, tuple[float, ReplayRun]] = OrderedDict()
        self._lock = Lock()

    def __len__(self) -> int:
        return len(self._items)

    def get(self, sid: str | None, scene: str | None = None) -> ReplayRun:
        now = time.monotonic()
        with self._lock:
            for key in [k for k, (seen, _) in self._items.items() if now - seen > self.ttl_s]:
                del self._items[key]
            key = sid or "anonymous-" + secrets.token_hex(4)
            if key in self._items:
                _, run = self._items.pop(key)
            else:
                run = ReplayRun(scene or "bodega")
            self._items[key] = (now, run)
            while len(self._items) > self.max_sessions:
                self._items.popitem(last=False)
        if scene in SCENES and run.scene != scene:
            with run.lock:
                run.reset(scene)
        return run
