"""Escena «Sentinel»: wAIrrior vigila todas las apps y contiene solo.

Replay determinista y sin red para la demo pública. Una sola ola con tres
ataques de esta semana —deshielo forzado en la cámara (patrón Europa
2-nov), cambio de IBAN por documento inyectado seguido de transferencia
(patrón Arkéa 4-nov) y llamadas con un token de agente robado (nuestro
incidente de octubre)— entra por los adaptadores reales de
``shield/autopilot`` (M10), se detecta y se contiene con su motor real
(``run_pipeline``/``ContainmentEngine``) y, en el frío, con el escudo
físico de ``shield/physics``. El 401 del atacante sale del gateway real
de Shield en memoria (``shield.gateway.create_app``): el token robado
funciona antes de la rotación y deja de funcionar después.

Todo número sale del código y va rotulado «simulated»: la ola es una
reconstrucción con eventos sintéticos, no telemetría de un negocio real.
Las cifras de las noticias son de sus fuentes, enlazadas en la página.
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import html
import json
import secrets
import time
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

import httpx
from fastapi.testclient import TestClient

from shield.autopilot import (
    ContainmentEngine,
    SecurityEvent,
    detect,
    from_cold_room,
    from_gateway_call,
    from_payment,
    from_pos_erp,
    run_pipeline,
)
from shield.autopilot.respond import TokenOps
from shield.gateway.app import UPSTREAM_KEY_NAME, create_app
from shield.physics.contract import ColdRoomParams, ProposedAction, RoomState
from shield.physics.gate import verify_action
from shield.physics.safe_state import last_safe_action
from shield.registry import Registry
from shield.schemas import AgentTokenStatus
from shield.vault import MemoryVault
from web.brand import BRAND, SUBTITLE, brand_mark_html, favicon_href
from web.physical_scene import trajectory_svg

SCENE = "sentinel"
T0 = datetime(2026, 11, 4, 2, 0, tzinfo=UTC)  # reloj simulado de la ola
FREEZER_SOURCES = (
    "https://www.tomshardware.com/tech-industry/cyber-security/supermarket-freezers-across-europe-struck-in-second-crippling-cyberattack-hackers-raise-temperatures-to-50-degrees-celsius-in-belgium-and-sweden-destroying-food-stocks",
    "https://www.cbsnews.com/news/europe-grocery-store-refrigerator-freezer-cyberattack-hack-food-wasted/",
    "https://www.aljazeera.com/news/2026/11/3/very-cold-war-whos-attacking-europes-supermarket-freezers",
)
ARKEA_SOURCES = (
    "https://www.euronews.com/2026/11/04/credit-mutuel-arkea-reports-cyberattack-says-clients-will-be-fully-protected",
    "https://www.lejdd.fr/economie/cyberattaque-le-credit-mutuel-arkea-victime-doperations-frauduleuses-des-millions-deuros-potentieles-detournes-187779",
)
APPS = (
    ("cold_room", "Cold room", "Cámara de frío"),
    ("payments", "Payments", "Pagos"),
    ("ai_gateway", "AI gateway", "Gateway de IA"),
    ("pos_erp", "POS / ERP", "POS / ERP"),
)


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


class _RegistryTokenOps(TokenOps):
    """TokenOps del autopiloto respaldado por el Registry real del gateway."""

    def __init__(self, registry: Registry, token_id: str) -> None:
        self._registry = registry
        self._old_id = token_id
        self._new_id: str | None = None
        self.new_raw: str = ""

    def rotate(self, actor: str) -> str:
        out = self._registry.rotate(self._old_id)
        if out is None:
            return ""
        token, raw = out
        self._new_id = token.token_id
        self.new_raw = raw
        return token.token_id

    def revoke(self, actor: str) -> None:
        self._registry.revoke(self._old_id)

    def restore(self, actor: str) -> None:
        # Deshacer la rotación (decisión del dueño): muere el token nuevo
        # y el anterior vuelve a ACTIVE en el Registry.
        if self._new_id:
            self._registry.revoke(self._new_id)
            self._new_id = None
        self._registry._set_status(self._old_id, AgentTokenStatus.ACTIVE)


def _upstream_ok(request: httpx.Request) -> httpx.Response:
    """Upstream simulado del gateway en memoria: nunca sale a la red."""
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-sentinel",
            "model": "muse-spark-1.3",
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


def _legit_events() -> list[SecurityEvent]:
    """Tráfico legítimo de fondo (simulated): debe pasar sin findings."""
    day = T0.replace(hour=10)  # horario normal; la ola llega a las 02:00
    return [
        from_payment({"actor": "billing-scheduled", "action": "transfer",
                      "target": "supplier:rent", "amount": 900, "beneficiary": "ES_RENT",
                      "ts": day}),
        from_payment({"actor": "billing-scheduled", "action": "transfer",
                      "target": "supplier:power", "amount": 210, "beneficiary": "ES_POWER",
                      "ts": day}),
        from_payment({"actor": "billing-scheduled", "action": "transfer",
                      "target": "supplier:rent", "amount": 900, "beneficiary": "ES_RENT",
                      "ts": day}),
        from_pos_erp({"actor": "pos-1", "action": "sale", "target": "ticket:1042", "ts": day}),
        from_pos_erp({"actor": "pos-1", "action": "sale", "target": "ticket:1043", "ts": day}),
        from_cold_room({"actor": "refrigeracion", "action": "set_setpoint", "value": 3.0,
                        "ts": day}),
        from_gateway_call({"agent": "bodega", "model": "sam-3.1", "ts": day, "cost_usd": 0.0025}),
    ]


class SentinelRun:
    """Una corrida «Sentinel» de un visitante: determinista, en memoria."""

    def __init__(self) -> None:
        self.lock = Lock()
        self._reset()

    def _reset(self) -> None:
        self.run_id = "sentinel_" + secrets.token_hex(6)
        self.replayed = False
        self.timeline: list[dict[str, Any]] = []
        self.measures: list[dict[str, Any]] = []
        self.pending_owner: list[str] = []
        self.total_ms = 0.0
        self.notice: dict[str, Any] = {}
        self.gateway: dict[str, Any] = {}
        self.cold: dict[str, Any] = {}
        self.released = False
        self.undone: set[str] = set()
        self._engines: list[ContainmentEngine] = []
        self._factor = hashlib.sha256(self.run_id.encode()).hexdigest()[:6]
        # Gateway real en memoria con un token de agente (el que roban).
        self._registry = Registry(":memory:")
        self._gateway_app = create_app(
            registry=self._registry,
            vault=MemoryVault({UPSTREAM_KEY_NAME: "sentinel-upstream-not-a-real-key"}),
            upstream_transport=httpx.MockTransport(_upstream_ok),
            sandbox=True,
        )
        self._gw = TestClient(self._gateway_app, raise_server_exceptions=False)
        token, raw = self._registry.create_token(
            "bodega", "crew", models=["muse-spark-1.3"], spend_cap_usd=5.0
        )
        self._stolen_token_id = token.token_id
        self._stolen_raw = raw
        legit = _legit_events()
        self.legit_allowed = len(legit) - len(detect(legit, legit))
        self.legit_counters = {
            "payments_ok": sum(1 for e in legit if e.app == "payments"),
            "pos_ok": sum(1 for e in legit if e.app == "pos_erp"),
            "cold_ok": sum(1 for e in legit if e.app == "cold_room"),
            "gateway_ok": sum(1 for e in legit if e.app == "ai_gateway"),
        }

    def reset(self) -> dict[str, Any]:
        self._reset()
        return self.state()

    # -- gateway real en memoria -------------------------------------------
    def _gw_call(self, raw: str) -> int:
        resp = self._gw.post(
            "/v1/chat/completions",
            json={"model": "muse-spark-1.3", "messages": [{"role": "user", "content": "ping"}]},
            headers={"Authorization": f"Bearer {raw}"},
        )
        return resp.status_code

    # -- la ola -------------------------------------------------------------
    def replay(self, lang: str = "en") -> dict[str, Any]:
        if self.replayed:
            return self.state()
        es = lang == "es"
        engines: list[ContainmentEngine] = []

        # 1) Frío: deshielo forzado de 4 h (patrón Europa 2-nov).
        cold_event = from_cold_room({
            "actor": "refrigeracion", "action": "defrost", "target": "camara",
            "duration_min": 240, "source": "attacker", "ts": T0,
        })
        cold_engine = ContainmentEngine()
        cold_incident, cold_result = run_pipeline([cold_event], engine=cold_engine)
        engines.append(cold_engine)
        params, room = ColdRoomParams(), RoomState()
        action = ProposedAction(
            kind="defrost", equipment="camara", duration_min=240,
            requested_by="refrigeracion", source="attacker",
        )
        verdict = verify_action(params, room, action)
        safe = last_safe_action(params, room)
        self.cold = {
            "decision": verdict.decision,
            "reason": verdict.reason,
            "peak_product_c": round(verdict.peak_product_c, 2),
            "predicted_breach_min": verdict.predicted_breach_min,
            "minutes_above_limit": round(verdict.minutes_above_limit, 1),
            "safe_setpoint_c": safe.value,
            "svg": trajectory_svg(
                verdict.baseline, verdict.with_action,
                safe_max_c=params.safe_max_c,
                breach_min=verdict.predicted_breach_min, lang=lang,
            ),
        }

        # 2) Pagos: IBAN cambiado por documento inyectado + transferencia.
        iban_event = from_pos_erp({
            "actor": "payments-bot", "action": "iban_change", "target": "supplier:acme",
            "source": "document", "iban_last4": "9999", "ts": T0 + timedelta(minutes=1),
        })
        pay_event = from_payment({
            "actor": "payments-bot", "action": "transfer", "target": "supplier:acme",
            "amount": 4800, "currency": "USD", "beneficiary": "ES_NEW_9999",
            "source": "document", "ts": T0 + timedelta(minutes=2),
        })
        pay_engine = ContainmentEngine()
        pay_incident, pay_result = run_pipeline(
            [iban_event, pay_event], _legit_events(), engine=pay_engine
        )
        engines.append(pay_engine)

        # 3) Gateway: ráfaga con el token robado; rotación real y 401 real.
        before = self._gw_call(self._stolen_raw)
        gw_ops = _RegistryTokenOps(self._registry, self._stolen_token_id)
        gw_engine = ContainmentEngine(token_ops=gw_ops)
        burst = [
            SecurityEvent(
                app="ai_gateway", actor="bodega", action="model_call",
                target="muse-spark-1.3", source="attacker",
                ts=T0 + timedelta(minutes=3, seconds=i),
                token_id=self._stolen_token_id,
                event_id=f"evt_stolen_{i:02d}",
            )
            for i in range(12)
        ]
        gw_incident, gw_result = run_pipeline(burst, engine=gw_engine)
        engines.append(gw_engine)
        after_attacker = self._gw_call(self._stolen_raw)
        # El token nuevo del agente legítimo sí pasa (200): no se apagó todo.
        legit_after = self._gw_call(gw_ops.new_raw) if gw_ops.new_raw else None
        self.gateway = {
            "attacker_before": before,
            "attacker_after": after_attacker,
            "legit_after": legit_after,
            "rotated": any(m.kind == "rotate_token" for m in gw_result.measures),
        }

        self._engines = engines
        results = [
            ("cold_room", cold_incident, cold_result, FREEZER_SOURCES),
            ("payments", pay_incident, pay_result, ARKEA_SOURCES),
            ("ai_gateway", gw_incident, gw_result, ()),
        ]
        self.total_ms = round(
            sum(r.detect_to_contain_ms for _, _, r, _ in results), 3
        )
        self.measures = [
            {**m.to_dict(), "undone": False}
            for _, _, r, _ in results for m in r.measures
        ]
        self.pending_owner = [
            p for _, _, r, _ in results for p in r.pending_owner
        ]
        self.timeline = [
            self._timeline_entry(app, inc, res, src, es)
            for app, inc, res, src in results
        ]
        self.notice = self._build_notice(es)
        self.replayed = True
        return self.state()

    def _timeline_entry(self, app, incident, result, sources, es: bool) -> dict[str, Any]:
        titles = {
            "cold_room": (
                "Forced 4 h defrost hits the cold room (Europe 2 Nov pattern)"
                if not es else
                "Deshielo forzado de 4 h contra la cámara (patrón Europa 2-nov)"
            ),
            "payments": (
                "Injected document changes a supplier IBAN, then a transfer follows (Arkéa pattern)"
                if not es else
                "Un documento inyectado cambia el IBAN de un proveedor y sigue una transferencia (patrón Arkéa)"
            ),
            "ai_gateway": (
                "Stolen agent token bursts calls through the AI gateway (our October incident)"
                if not es else
                "Un token de agente robado dispara llamadas por el gateway de IA (nuestro incidente de octubre)"
            ),
        }
        contained = {
            "cold_room": (
                "kept in last safe state" if not es else "quedó en su último estado seguro"
            ),
            "payments": (
                "transfer held, IBAN change frozen"
                if not es else "transferencia retenida, cambio de IBAN congelado"
            ),
            "ai_gateway": (
                "token rotated: attacker 401"
                if not es else "token rotado: el atacante recibe 401"
            ),
        }
        return {
            "app": app,
            "title": titles[app],
            "findings": [f.reason for f in incident.findings],
            "severity": incident.severity,
            "contained": contained[app],
            "detect_to_contain_ms": round(result.detect_to_contain_ms, 3),
            "sources": list(sources),
            "simulated": True,
        }

    def _build_notice(self, es: bool) -> dict[str, Any]:
        labels = {
            "block_action": ("Blocked the malicious action", "Bloqueamos la acción maliciosa"),
            "hold_payment": ("Held the transfer (not executed)", "Retuvimos la transferencia (no ejecutada)"),
            "safe_state": ("Kept the cold room in its last safe state", "Dejamos la cámara en su último estado seguro"),
            "rotate_token": ("Rotated the stolen gateway token — attacker now gets 401", "Rotamos el token robado del gateway: el atacante ahora recibe 401"),
            "revoke_tokens": ("Revoked the attacker's token", "Revocamos el token del atacante"),
            "read_only": ("Put the app in read-only mode", "Pasamos la app a solo lectura"),
            "circuit_breaker": ("Froze writes for the flagged actors", "Congelamos las escrituras de los actores marcados"),
            "log": ("Logged the event", "Registramos el evento"),
        }
        seen: list[str] = []
        for m in self.measures:
            pair = labels.get(m["kind"])
            if pair and pair[es] not in seen:
                seen.append(pair[es])
        return {
            "title": (
                "You were attacked. We already did:" if not es
                else "Fuiste atacado. Ya hicimos:"
            ),
            "already_did": seen,
            "pending_owner": self.pending_owner,
            "simulated": True,
        }

    # -- acciones del dueño ---------------------------------------------------
    def undo(self, undo_id: str) -> dict[str, Any]:
        for engine in self._engines:
            if engine.undo(undo_id):
                self.undone.add(undo_id)
                for m in self.measures:
                    if m["undo_id"] == undo_id:
                        m["undone"] = True
                return {"status": "ok", "undo_id": undo_id, "state": self.state()}
        return {"status": "error", "error": "unknown undo_id", "error_code": "no_measure"}

    def release(self, factor: str) -> dict[str, Any]:
        """Libera lo irreversible solo con el segundo factor (simulado)."""
        if not self.replayed:
            return {"status": "error", "error": "nothing to release", "error_code": "no_replay"}
        if (factor or "").strip() != self._factor:
            return {
                "status": "error", "error": "bad second factor",
                "error_code": "bad_factor",
            }
        self.released = True
        return {"status": "ok", "released": True, "simulated": True, "state": self.state()}

    # -- estado público ---------------------------------------------------------
    def state(self) -> dict[str, Any]:
        contained_apps = {e["app"] for e in self.timeline}
        if self.replayed:
            contained_apps |= {"pos_erp"}
        apps = []
        for key, en, es in APPS:
            apps.append({
                "app": key,
                "name_en": en,
                "name_es": es,
                "status": "contained" if key in contained_apps else "ok",
            })
        return {
            "run_id": self.run_id,
            "scene": SCENE,
            "simulated": True,
            "total_cost_usd": 0.0,
            "replayed": self.replayed,
            "apps": apps,
            "timeline": self.timeline,
            "measures": self.measures,
            "pending_owner": self.pending_owner,
            "detect_to_contain_ms": self.total_ms,
            "notice": self.notice,
            "gateway": self.gateway,
            "cold": self.cold,
            "legit_allowed": self.legit_allowed,
            "legit_counters": self.legit_counters,
            "released": self.released,
            "second_factor_demo": self._factor if self.replayed else "",
        }


class SentinelStore:
    """Corridas «Sentinel» por visitante: en memoria, con tope y caducidad."""

    def __init__(self, *, max_sessions: int = 200, ttl_s: float = 1800.0) -> None:
        self.max_sessions = max_sessions
        self.ttl_s = ttl_s
        self._items: OrderedDict[str, tuple[float, SentinelRun]] = OrderedDict()
        self._lock = Lock()

    def __len__(self) -> int:
        return len(self._items)

    def get(self, sid: str | None) -> SentinelRun:
        now = time.monotonic()
        with self._lock:
            for key in [k for k, (seen, _) in self._items.items() if now - seen > self.ttl_s]:
                del self._items[key]
            key = sid or "anonymous-sentinel"
            if key in self._items:
                _, run = self._items.pop(key)
            else:
                run = SentinelRun()
            self._items[key] = (now, run)
            while len(self._items) > self.max_sessions:
                self._items.popitem(last=False)
        return run


SENTINEL_T: dict[str, dict[str, str]] = {
    "en": {
        "label": "REPLAY — simulated attack wave; the containment engine and gateway are real, in memory",
        "hero": "One sentinel over every app and machine your business runs.",
        "headline": "Three of this week's real attacks arrive at once. wAIrrior contains each one on its own — in milliseconds — and only the irreversible waits for you.",
        "replay_btn": "Replay this week's attacks",
        "new_run": "New run",
        "detected_contained": "detected → contained",
        "ms": "ms",
        "not_run": "Press the button: the wave is simulated, the engine is real.",
        "timeline": "Timeline",
        "ok": "protected",
        "contained": "CONTAINED",
        "legit_title": "Legitimate work keeps flowing (simulated background)",
        "payments_ok": "recurring payments OK",
        "pos_ok": "POS sales OK",
        "cold_ok": "other equipment OK",
        "gateway_ok": "legit AI calls OK",
        "cold_card": "Cold room — predicted product temperature (simulated)",
        "kept_safe": "kept in last safe state",
        "pay_detail": "transfer held, IBAN change frozen",
        "gw_detail": "token rotated: attacker",
        "pos_detail": "IBAN change frozen",
        "peak": "Predicted product peak",
        "breach": "Breaks 5 °C at minute",
        "undo": "Undo",
        "undone": "undone",
        "release": "Release with 2nd factor",
        "release_hint": "Irreversible (execute the held transfer / make the IBAN change final) needs your second factor. Simulated demo code:",
        "release_code_ph": "6-digit demo code",
        "released": "Released by the owner with a second factor (simulated): the held items are now yours to execute in your bank app — wAIrrior never pays on its own.",
        "bad_factor": "Wrong code — nothing was released.",
        "sources": "News sources",
        "october": "Our own October incident: a leaked AI key, ~16 h of abuse, USD 310 (internal record, recorded runs in this repo).",
        "simulated": "simulated",
        "scene": "Scene",
        "footer_meta": "Built on Meta's Muse models; independent project, not affiliated with or endorsed by Meta.",
        "footer_hack": "Built during the hackathon, 26 Oct – 4 Nov 2026.",
    },
    "es": {
        "label": "REPETICIÓN — ola de ataques simulada; el motor de contención y el gateway son reales, en memoria",
        "hero": "Un solo vigía sobre todas las apps y máquinas de tu negocio.",
        "headline": "Tres ataques reales de esta semana llegan a la vez. wAIrrior contiene cada uno solo —en milisegundos— y solo lo irreversible te espera a ti.",
        "replay_btn": "Repetir los ataques de esta semana",
        "new_run": "Nueva corrida",
        "detected_contained": "detectado → contenido",
        "ms": "ms",
        "not_run": "Pulsa el botón: la ola es simulada, el motor es real.",
        "timeline": "Línea de tiempo",
        "ok": "protegido",
        "contained": "CONTENIDO",
        "legit_title": "El trabajo legítimo sigue fluyendo (fondo simulado)",
        "payments_ok": "pagos recurrentes OK",
        "pos_ok": "ventas POS OK",
        "cold_ok": "otros equipos OK",
        "gateway_ok": "llamadas IA legítimas OK",
        "cold_card": "Cámara de frío — temperatura predicha del producto (simulado)",
        "kept_safe": "quedó en su último estado seguro",
        "pay_detail": "transferencia retenida, cambio de IBAN congelado",
        "gw_detail": "token rotado: el atacante recibe",
        "pos_detail": "cambio de IBAN congelado",
        "peak": "Pico predicho del producto",
        "breach": "Rompe 5 °C al minuto",
        "undo": "Deshacer",
        "undone": "deshecho",
        "release": "Liberar con segundo factor",
        "release_hint": "Lo irreversible (ejecutar la transferencia retenida / dejar fijo el cambio de IBAN) necesita tu segundo factor. Código demo simulado:",
        "release_code_ph": "código demo de 6 dígitos",
        "released": "Liberado por el dueño con segundo factor (simulado): lo retenido queda para que tú lo ejecutes en tu banco — wAIrrior nunca paga solo.",
        "bad_factor": "Código incorrecto: no se liberó nada.",
        "sources": "Fuentes de las noticias",
        "october": "Nuestro incidente de octubre: una llave de IA filtrada, ~16 h de abuso, USD 310 (registro interno, corridas grabadas en este repo).",
        "simulated": "simulado",
        "scene": "Escena",
        "footer_meta": "Construido sobre los modelos Muse de Meta; proyecto independiente, sin afiliación ni respaldo de Meta.",
        "footer_hack": "Construido durante el hackathon, del 26 de octubre al 4 de noviembre de 2026.",
    },
}


def _st(lang: str, key: str) -> str:
    return SENTINEL_T.get(lang, SENTINEL_T["en"]).get(key, SENTINEL_T["en"].get(key, key))


_CSS = """
:root{--bg:#0a0d12;--surface:#10151c;--sunk:#0c1016;--line:#212935;--line-strong:#2f3946;--text:#e8ecf2;--muted:#9aa5b4;--ok:#36b37e;--ok-text:#7fe0b4;--bad:#e5534b;--bad-text:#ffaaa3;--warn:#efa83a;--warn-text:#ffd28a;--sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;--mono:ui-monospace,Menlo,Consolas,monospace}
*{box-sizing:border-box}[hidden]{display:none!important}body{margin:0;background:var(--bg);color:var(--text);font-family:var(--sans);font-size:17px;line-height:1.5}
a{color:#ffd28a}.wrap{width:min(1760px,calc(100% - 48px));margin:0 auto}
.band{border-bottom:1px solid var(--line)}.band .inner{width:min(1760px,calc(100% - 48px));margin:0 auto;padding:14px 0 10px}
.band-top{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;justify-content:space-between}
.brandline{margin:0;color:var(--muted)}.brandline strong{color:var(--text);font-size:18px}
.live-label{border:1px solid rgba(239,168,58,.5);border-radius:6px;color:var(--warn-text);background:rgba(239,168,58,.08);padding:5px 10px;font-size:13px;font-weight:600}
.mode-switch,.lang{display:inline-flex;gap:2px;padding:2px;border:1px solid var(--line);border-radius:10px;background:var(--surface)}
.mode-switch a,.lang a{display:inline-flex;align-items:center;min-height:36px;padding:6px 12px;color:var(--muted);border-radius:8px;text-decoration:none;font-size:14px;font-weight:550}
.mode-switch a[aria-current="true"],.lang a[aria-current="true"]{background:#151b24;color:var(--text)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;padding:9px 18px;border:1px solid var(--line-strong);border-radius:10px;background:#151b24;color:var(--text);font:inherit;font-size:15px;font-weight:600;cursor:pointer}
.btn.primary{background:#efa83a;border-color:#efa83a;color:#241703}.btn.small{min-height:36px;padding:5px 12px;font-size:14px}
.btn:disabled{opacity:.45;cursor:default}
.hero{padding:12px 0 4px;text-align:center}.hero-brand{font-size:clamp(44px,4vw,64px);font-weight:800;letter-spacing:-.04em;margin:0;line-height:.95}
.hero-fill{color:#E8A33D}.hero-outline{color:transparent;-webkit-text-stroke:2px rgba(255,255,255,.92)}
.hero-sub{margin:12px auto 0;max-width:900px;font-size:clamp(22px,2.2vw,32px);font-weight:650;line-height:1.25}
.hero-note{margin:10px auto 0;max-width:820px;color:var(--muted);font-size:17px}
.apps{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}
.app-card{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:14px 18px}
.app-card h3{margin:0 0 4px;font-size:19px}.app-status{font-weight:700;font-size:14px}
.app-card[data-state="ok"] .app-status{color:var(--ok-text)}.app-card[data-state="contained"]{border-color:rgba(239,168,58,.65)}
.app-card[data-state="contained"] .app-status{color:var(--warn-text)}
.app-detail{color:var(--muted);font-size:14px;margin:4px 0 0}
.counter{text-align:center;margin:4px 0 2px}.counter b{font-size:50px;letter-spacing:-.02em;color:var(--warn-text)}
.counter span{display:block;color:var(--muted);font-size:15px}
.grid{display:grid;grid-template-columns:1.25fr .9fr;gap:14px;align-items:start;margin:14px 0}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:16px 20px}
.panel h2{margin:0 0 10px;font-size:21px}
.tl{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px}
.tl li{border:1px solid var(--line);border-radius:8px;padding:10px 14px;background:var(--sunk)}
.tl .t-head{display:flex;gap:10px;flex-wrap:wrap;align-items:baseline}.tl .t-title{font-weight:650;flex:1}
.tl .ms{font-family:var(--mono);color:var(--warn-text);font-size:14px}
.tl p{margin:4px 0;color:var(--muted);font-size:15px}
.chip{display:inline-flex;padding:2px 10px;border-radius:6px;font-size:13px;font-weight:700;background:rgba(239,168,58,.14);color:var(--warn-text);border:1px solid rgba(239,168,58,.5)}
.chip.allow{background:rgba(54,179,126,.14);color:var(--ok-text);border-color:rgba(54,179,126,.5)}
.chart{border:1px solid var(--line);border-radius:8px;overflow:hidden;margin-top:10px}
.chat{background:#0b1410;border:1px solid rgba(54,179,126,.4);border-radius:8px;padding:14px 18px}
.chat-text{font-size:19px;font-weight:600}.chat ol{margin:8px 0;padding-left:22px}.chat li{margin:4px 0}
.measure{display:flex;gap:8px;align-items:center;flex-wrap:wrap;border-top:1px solid var(--line);padding:8px 0;font-size:15px}
.measure code{font-family:var(--mono);font-size:13px;color:var(--muted)}
input[type="text"]{min-height:40px;padding:8px 12px;font:inherit;background:var(--sunk);border:1px solid var(--line-strong);border-radius:8px;color:var(--text)}
.hint{color:var(--muted);font-size:14px}.mono{font-family:var(--mono)}
.legit{display:flex;gap:12px;flex-wrap:wrap}.legit .fact{background:var(--sunk);border:1px solid rgba(54,179,126,.35);border-radius:8px;padding:8px 14px}
.legit b{font-size:24px;color:var(--ok-text)}
.footer{border-top:1px solid var(--line);color:var(--muted);font-size:14px;padding:22px 0 34px}
@media (max-width:900px){.apps{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

_JS = r"""
const TEXT = __TEXTS__;
let RUN_ID = null;
function el(tag, text, cls) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = String(text); return n; }
function byId(id) { return document.getElementById(id); }
function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
async function api(path, opts) { const q = "?lang=" + TEXT.lang_code; const res = await fetch(path + q, opts || {}); const data = await res.json().catch(() => ({})); if (data.run_id) RUN_ID = data.run_id; return {res, data}; }
function appName(a) { return TEXT.lang_code === "es" ? a.name_es : a.name_en; }
function render(data) {
  const apps = byId("apps"); clear(apps);
  (data.apps || []).forEach((a) => {
    const card = el("div", null, "app-card"); card.dataset.state = a.status;
    card.appendChild(el("h3", appName(a)));
    card.appendChild(el("div", a.status === "contained" ? TEXT.contained : "● " + TEXT.ok, "app-status"));
    const detail = {cold_room: TEXT.kept_safe, payments: TEXT.pay_detail, ai_gateway: TEXT.gw_detail + " " + ((data.gateway || {}).attacker_after || "401"), pos_erp: TEXT.pos_detail}[a.app];
    if (a.status === "contained" && detail) card.appendChild(el("p", detail, "app-detail"));
    apps.appendChild(card);
  });
  const c = data.legit_counters || {};
  byId("cPayments").textContent = c.payments_ok || 0; byId("cPos").textContent = c.pos_ok || 0;
  byId("cCold").textContent = c.cold_ok || 0; byId("cGateway").textContent = c.gateway_ok || 0;
  byId("bigMs").textContent = data.replayed ? Number(data.detect_to_contain_ms || 0).toFixed(1) + " ms" : "—";
  const tl = byId("timeline"); clear(tl);
  if (!data.replayed) { tl.appendChild(el("li", TEXT.not_run)); }
  (data.timeline || []).forEach((e2) => {
    const li = el("li");
    const head = el("div", null, "t-head");
    head.appendChild(el("span", e2.title, "t-title"));
    head.appendChild(el("span", e2.detect_to_contain_ms + " ms", "ms"));
    li.appendChild(head);
    (e2.findings || []).forEach((f) => li.appendChild(el("p", f)));
    const chip = el("span", TEXT.contained + " — " + e2.contained, "chip"); li.appendChild(chip);
    li.appendChild(el("span", " simulated", "hint"));
    if ((e2.sources || []).length) { const p = el("p", TEXT.sources + ": "); e2.sources.forEach((u, i) => { const a = el("a", "[" + (i + 1) + "]"); a.href = u; a.target = "_blank"; a.rel = "noopener"; p.appendChild(a); p.appendChild(el("span", " ")); }); li.appendChild(p); }
    tl.appendChild(li);
  });
  const cold = byId("coldBody"); clear(cold);
  if (data.cold && data.cold.svg) {
    cold.appendChild(el("p", TEXT.kept_safe + " · setpoint " + data.cold.safe_setpoint_c + " °C · " + TEXT.peak + " " + data.cold.peak_product_c + " °C · " + TEXT.breach + " " + data.cold.predicted_breach_min));
    const chart = el("div", null, "chart"); chart.innerHTML = data.cold.svg; cold.appendChild(chart);
  } else { cold.appendChild(el("p", TEXT.not_run, "hint")); }
  const notice = byId("notice"); clear(notice);
  if (data.notice && data.notice.title) {
    notice.appendChild(el("p", data.notice.title, "chat-text"));
    const ol = el("ol"); (data.notice.already_did || []).forEach((item, i) => ol.appendChild(el("li", item))); notice.appendChild(ol);
    const byKind = {};
    (data.measures || []).forEach((m) => { (byKind[m.kind + "|" + m.app] = byKind[m.kind + "|" + m.app] || []).push(m); });
    Object.values(byKind).forEach((group) => {
      const m = group[0];
      const row = el("div", null, "measure");
      row.appendChild(el("code", m.kind + " · " + m.app));
      const b = el("button", m.undone ? TEXT.undone : TEXT.undo, "btn small"); b.type = "button"; b.disabled = !!m.undone;
      b.addEventListener("click", async () => { const form = new FormData(); form.append("undo_id", m.undo_id); const r = await api("/sentinel/undo", {method: "POST", body: form}); render(r.data.state || r.data); });
      row.appendChild(b); notice.appendChild(row);
    });
    (data.pending_owner || []).forEach((p) => notice.appendChild(el("p", "⏳ " + p, "hint")));
    byId("releaseBox").hidden = false;
    byId("demoCode").textContent = data.second_factor_demo || "";
    if (data.released) { byId("releaseLine").textContent = TEXT.released; byId("releaseBtn").disabled = true; }
  }
}
async function refresh() { const {data} = await api("/sentinel/state"); render(data); return data; }
async function runReplay() { const btn = byId("replayBtn"); btn.disabled = true; const {data} = await api("/sentinel/replay", {method: "POST"}); render(data); btn.disabled = false; }
document.addEventListener("DOMContentLoaded", () => {
  byId("replayBtn").addEventListener("click", runReplay);
  byId("newRunBtn").addEventListener("click", async () => { await fetch("/sentinel/reset?lang=" + TEXT.lang_code, {method: "POST"}); window.location.href = "/?scene=sentinel&lang=" + TEXT.lang_code; });
  byId("releaseBtn").addEventListener("click", async () => { const form = new FormData(); form.append("factor", byId("factorInput").value); const {res, data} = await api("/sentinel/release", {method: "POST", body: form}); if (res.ok && data.released) { render(data.state); byId("releaseLine").textContent = TEXT.released; } else { byId("releaseLine").textContent = TEXT.bad_factor; } });
  refresh().then(() => { if (new URLSearchParams(window.location.search).get("autorun") === "1") runReplay(); }).catch(() => {});
  // Fondo legítimo simulado: sigue contando tras la contención.
  const keys = ["cPayments", "cPos", "cCold", "cGateway"]; let tick = 0;
  setInterval(() => { const n = byId(keys[tick % keys.length]); if (n) n.textContent = String(Number(n.textContent || 0) + 1); tick += 1; }, 1600);
});
"""


def _hero_brand() -> str:
    from web.brand import brand_parts

    return "".join(
        f"<span class='hero-{'fill' if kind == 'ai' else 'outline'}'>{_e(text)}</span>"
        for kind, text in brand_parts(BRAND)
    )


def render_sentinel_page(lang: str = "en") -> str:
    """Página pública de la escena «Sentinel» (oscura, ámbar, 1920×1080)."""
    lang = lang if lang in SENTINEL_T else "en"

    def t(key: str) -> str:
        return _st(lang, key)

    labels = dict(SENTINEL_T[lang])
    labels["lang_code"] = lang
    script = _JS.replace("__TEXTS__", json.dumps(labels, ensure_ascii=False))
    apps_html = "".join(
        f"<div class='app-card' data-state='ok'><h3>{_e(en if lang == 'en' else es)}</h3>"
        f"<div class='app-status'>● {_e(t('ok'))}</div></div>"
        for _key, en, es in APPS
    )
    en_cur = " aria-current='true'" if lang == "en" else ""
    es_cur = " aria-current='true'" if lang == "es" else ""
    return (
        "<!doctype html>\n"
        f"<html lang='{_e(lang)}'><head><meta charset='utf-8'>"
        f"<link rel='icon' href=\"{favicon_href()}\">"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_e(BRAND)} — Sentinel · {_e(SUBTITLE)}</title>"
        f"<style>{_CSS}</style></head><body>"
        "<header class='band'><div class='inner'><div class='band-top'>"
        f"<p class='brandline'><strong>{brand_mark_html()}</strong> · {_e(SUBTITLE)}</p>"
        f"<span class='live-label'>{_e(t('label'))}</span>"
        "<div style='display:flex;gap:8px;flex-wrap:wrap'>"
        f"<nav class='mode-switch scene-switch' aria-label='{_e(t('scene'))}'>"
        f"<a href='/?scene=bodega&lang={lang}'>{_e('Warehouse' if lang == 'en' else 'Bodega')}</a>"
        f"<a href='/?scene=frio&lang={lang}'>{_e('Cold chain' if lang == 'en' else 'Cadena de frío')}</a>"
        f"<a href='/?scene=physical&lang={lang}'>Physical</a>"
        f"<a href='/?scene=sentinel&lang={lang}' aria-current='true'>Sentinel</a></nav>"
        f"<span class='lang'><a href='/?scene=sentinel&lang=en'{en_cur}>EN</a>"
        f"<a href='/?scene=sentinel&lang=es'{es_cur}>ES</a></span>"
        f"<button class='btn ghost' id='newRunBtn' type='button'>{_e(t('new_run'))}</button>"
        "</div></div>"
        "<div class='hero'>"
        f"<p class='hero-brand' aria-hidden='true'>{_hero_brand()}</p>"
        f"<p class='hero-sub'>{_e(t('hero'))}</p>"
        f"<p class='hero-note'>{_e(t('headline'))}</p>"
        f"<p><button class='btn primary' id='replayBtn' type='button'>{_e(t('replay_btn'))}</button></p>"
        "</div></div></header>"
        "<main class='wrap'>"
        f"<section id='apps' class='apps' aria-live='polite'>{apps_html}</section>"
        f"<div class='counter'><b id='bigMs'>—</b><span>{_e(t('detected_contained'))} · {_e(t('simulated'))}</span></div>"
        "<div class='grid'>"
        f"<section class='panel'><h2>{_e(t('timeline'))}</h2><ul class='tl' id='timeline'></ul>"
        f"<h2 style='margin-top:18px'>{_e(t('legit_title'))}</h2><div class='legit'>"
        f"<span class='fact'><b id='cPayments'>0</b> {_e(t('payments_ok'))}</span>"
        f"<span class='fact'><b id='cPos'>0</b> {_e(t('pos_ok'))}</span>"
        f"<span class='fact'><b id='cCold'>0</b> {_e(t('cold_ok'))}</span>"
        f"<span class='fact'><b id='cGateway'>0</b> {_e(t('gateway_ok'))}</span></div>"
        f"<p class='hint'>{_e(t('october'))}</p></section>"
        f"<section class='panel'><h2>{_e(t('cold_card'))}</h2><div id='coldBody'></div>"
        f"<h2 style='margin-top:18px'>WhatsApp · {_e(t('simulated'))}</h2>"
        "<div class='chat' id='notice'></div>"
        "<div id='releaseBox' hidden>"
        f"<p class='hint'>{_e(t('release_hint'))} <span class='mono' id='demoCode'></span></p>"
        f"<input type='text' id='factorInput' placeholder='{_e(t('release_code_ph'))}' autocomplete='off'> "
        f"<button class='btn primary' id='releaseBtn' type='button'>{_e(t('release'))}</button>"
        "<p class='hint' id='releaseLine' aria-live='polite'></p></div>"
        "</section></div>"
        "</main>"
        f"<footer class='wrap footer'><p>{_e(t('sources'))}: "
        + " ".join(
            f"<a href='{_e(u)}' target='_blank' rel='noopener'>[{i + 1}]</a>"
            for i, u in enumerate(FREEZER_SOURCES + ARKEA_SOURCES)
        )
        + f"</p><p>{_e(t('footer_meta'))}</p><p>{_e(t('footer_hack'))}</p></footer>"
        f"<script>{script}</script></body></html>"
    )
