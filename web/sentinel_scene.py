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
from shield.autopilot.respond import (
    TokenOps,
    _fmt_amount,
    _pretty_supplier,
    possessive_en,
)
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

    def __init__(self, registry: Registry, token_id: str, agent: str = "bodega") -> None:
        self._registry = registry
        self._old_id = token_id
        self._agent = agent
        self._new_id: str | None = None
        self.new_raw: str = ""

    def rotate(self, actor: str) -> str:
        if actor != self._agent:
            return ""  # otros actores no tienen llave en este gateway
        out = self._registry.rotate(self._old_id)
        if out is None:
            return ""
        token, raw = out
        self._new_id = token.token_id
        self.new_raw = raw
        return token.token_id

    def revoke(self, actor: str) -> None:
        # El motor global revoca; aquí la llave robada se reemplaza de una
        # vez (rotación real en el Registry): la vieja da 401 y nace otra.
        if actor == self._agent and self._new_id is None:
            self.rotate(actor)

    def restore(self, actor: str) -> None:
        # Deshacer la rotación (decisión del dueño): muere el token nuevo
        # y el anterior vuelve a ACTIVE en el Registry. Solo para el agente
        # dueño de la llave: deshacer otra medida no revive la robada.
        if actor != self._agent:
            return
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


APP_NAMES: dict[str, tuple[str, str]] = {key: (en, es) for key, en, es in APPS}
ACTOR_APP = {"refrigeracion": "cold_room", "payments-bot": "payments", "bodega": "ai_gateway"}


def measure_label(m: dict[str, Any], ctx: dict[str, Any], lang: str) -> str:
    """Etiqueta de una medida: «App: qué se hizo», con datos de la ola.

    ``ctx`` trae lo que la ola sabe de cada ataque (duración del deshielo,
    monto y proveedor del pago, tamaño de la ráfaga, agente de la llave).
    """
    es = lang == "es"
    kind, app, target, detail = m["kind"], m["app"], m["target"], m.get("detail", "")
    owner_app = ACTOR_APP.get(target, app) if app == "*" else app
    name = APP_NAMES.get(owner_app, ("All apps", "Todas las apps"))[1 if es else 0]
    supplier = ctx.get("supplier", "the supplier")
    amount = ctx.get("amount", "")
    if kind == "block_action" and app == "cold_room":
        hours = ctx.get("defrost_hours", "")
        what = (f"deshielo de {hours} horas bloqueado" if es
                else f"blocked the {hours}-hour defrost")
    elif kind == "safe_state":
        what = (f"se mantiene en su último ajuste seguro ({ctx.get('safe_c', 3.0):g} °C)" if es
                else f"kept at its last safe setting ({ctx.get('safe_c', 3.0):g} °C)")
    elif kind == "block_action" and app == "pos_erp":
        what = (f"cambio de datos bancarios de {supplier} bloqueado" if es
                else f"{possessive_en(supplier)} bank-details change blocked")
    elif kind in ("hold_payment", "block_action") and app == "payments":
        what = (f"transferencia de {amount} a {supplier} retenida" if es
                else f"transfer of {amount} to {supplier} held")
    elif kind == "block_action" and app == "ai_gateway":
        n = ctx.get("burst", 0)
        what = (f"{n} llamadas con la llave robada bloqueadas" if es
                else f"{n} calls with the stolen key blocked")
    elif (kind in ("revoke_tokens", "rotate_token", "freeze_actor_writes")
          and target == ctx.get("stolen_agent")):
        # Revocar y congelar al mismo agente es una sola decisión de negocio.
        what = ("llave robada reemplazada y agente congelado" if es
                else "stolen key replaced, agent frozen")
    elif kind in ("revoke_tokens", "freeze_actor_writes"):
        what = (f"agente {target}: llaves revocadas y escrituras congeladas" if es
                else f"agent {target}: keys revoked, writes frozen")
    elif kind == "circuit_breaker":
        name = "Todas las apps" if es else "All apps"
        what = ("escrituras de agentes en pausa" if es else "agent writes paused")
    elif kind == "freeze_app_scope":
        what = (f"operación «{detail or target}» congelada" if es
                else f"operation '{detail or target}' frozen")
    elif kind == "read_only":
        what = "en solo lectura" if es else "read-only"
    else:
        what = "registrado" if es else "logged"
    return f"{name}: {what}"


def _background_300() -> list[SecurityEvent]:
    """300 operaciones legítimas de fondo (misma semilla fija que el bench M10).

    Solo sirven para contar, con ``engine.allows_write`` del motor real,
    cuántas seguirían vivas tras la contención. Todo simulated.
    """
    import random

    rng = random.Random(20261104)
    out: list[SecurityEvent] = []
    for i in range(300):
        app = ("payments", "pos_erp", "cold_room", "ai_gateway")[i % 4]
        ts = T0.replace(hour=10) + timedelta(seconds=rng.randrange(0, 600))
        if app == "payments":
            raw = {"app": app, "actor": "payments-bot", "action": "transfer",
                   "target": "supplier:known", "ts": ts.isoformat(),
                   "source": "human" if (i // 4) % 2 == 0 else "agent",
                   "values": {"amount": rng.randrange(400, 601),
                              "beneficiary": "KNOWN", "beneficiary_known": True}}
        elif app == "pos_erp":
            raw = {"app": app, "actor": "erp-bot", "action": "supplier_change",
                   "target": f"supplier:known-{i % 5}", "ts": ts.isoformat(),
                   "values": {"field": "contact"}}
        elif app == "cold_room":
            raw = {"app": app, "actor": "refrigeracion", "action": "set_setpoint",
                   "target": f"camara-{2 + i % 3}", "ts": ts.isoformat(),
                   "values": {"value": 3.0}}
        else:
            raw = {"app": app, "actor": "ops-bot", "action": "model_call",
                   "target": "muse-spark-1.3", "ts": ts.isoformat(),
                   "token_id": "tok-ops", "values": {"cost_usd": 1}}
        out.append(SecurityEvent.from_dict(raw))
    return out


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
        self.pending_owner: dict[str, list[str]] = {}
        self.legit_still_running = 300
        self.still_breakdown: dict[str, Any] = {}
        self.scope_level = "none"
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
        # La ola completa entra como UN incidente correlacionado al motor
        # real de M10 (3 apps, 3 actores): nivel global, con la exención de
        # las operaciones humanas recurrentes que el propio motor aplica.
        cold_event = from_cold_room({
            "actor": "refrigeracion", "action": "defrost", "target": "camara",
            "duration_min": 240, "source": "attacker", "ts": T0,
        })
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
                legend_top=True,
            ),
        }

        # Pagos: IBAN cambiado por documento inyectado + transferencia.
        iban_event = from_pos_erp({
            "actor": "payments-bot", "action": "iban_change", "target": "supplier:Acme-Foods",
            "source": "document", "iban_last4": "9999", "ts": T0 + timedelta(minutes=1),
        })
        pay_event = from_payment({
            "actor": "payments-bot", "action": "transfer", "target": "supplier:Acme-Foods",
            "amount": 4800, "currency": "USD", "beneficiary": "ES_NEW_9999",
            "source": "document", "ts": T0 + timedelta(minutes=2),
        })
        # Gateway: ráfaga con el token robado (antes de contener pasa, 200).
        before = self._gw_call(self._stolen_raw)
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
        gw_ops = _RegistryTokenOps(self._registry, self._stolen_token_id)
        engine = ContainmentEngine(token_ops=gw_ops)
        events = [cold_event, iban_event, pay_event, *burst]
        incident, result = run_pipeline(events, _legit_events(), engine=engine)
        self._engines = [engine]
        after_attacker = self._gw_call(self._stolen_raw)
        # La llave nueva del agente legítimo sí pasa (200): no se apagó todo.
        legit_after = self._gw_call(gw_ops.new_raw) if gw_ops.new_raw else None
        self.gateway = {
            "attacker_before": before,
            "attacker_after": after_attacker,
            "legit_after": legit_after,
            "rotated": after_attacker == 401 and legit_after == 200,
        }
        self.total_ms = round(result.detect_to_contain_ms, 3)
        # Lo que la ola sabe de cada ataque, para rotular cada medida.
        ctx = {
            "defrost_hours": f"{float(cold_event.values.get('duration_min') or 0) / 60:g}",
            "safe_c": float(safe.value),
            "supplier": _pretty_supplier(pay_event.target),
            "amount": _fmt_amount(pay_event),
            "burst": len(burst),
            "stolen_agent": "bodega",
        }
        self.measures = []
        for m in result.measures:
            d = {**m.to_dict(), "undone": False}
            d["label_en"] = measure_label(d, ctx, "en")
            d["label_es"] = measure_label(d, ctx, "es")
            self.measures.append(d)
        # Operaciones legítimas que el motor deja vivas tras la contención.
        background = _background_300()
        kept = [e for e in background if engine.allows_write(e)]
        self.legit_still_running = len(kept)
        # Por qué esa cifra: desglose leído del motor, no escrito a mano.
        self.still_breakdown = {
            "scope_level": result.scope_level,
            "human_known_payments_kept": sum(
                1 for e in kept if e.source == "human" and e.app == "payments"
                and e.values.get("beneficiary_known")),
            "other_kept": sum(
                1 for e in kept if not (e.source == "human" and e.app == "payments")),
            "agent_writes_paused": sum(
                1 for e in background if e.source != "human" and not engine.allows_write(e)),
            "human_paused": sum(
                1 for e in background if e.source == "human" and not engine.allows_write(e)),
            "total": len(background),
        }
        self.scope_level = result.scope_level
        self.timeline = self._timeline(incident, lang)
        # Aviso de negocio de M10, tal cual sale del motor (EN y ES).
        self.notice = {
            "text_en": result.notice_en,
            "text_es": result.notice_es,
            "simulated": True,
        }
        self.pending_owner = self._pending_business()
        self.replayed = True
        return self.state()

    def _finding_texts(self, kind: str, es: bool) -> str:
        """Frase de negocio por tipo de hallazgo (la razón cruda no se muestra)."""
        peak = self.cold.get("peak_product_c", "?")
        breach = self.cold.get("predicted_breach_min", "?")
        texts = {
            "defrost_anomaly": (
                "A forced 4-hour defrost, outside the scheduled window"
                if not es else
                "Un deshielo forzado de 4 horas, fuera del horario programado"
            ),
            "physics_block": (
                f"The physics check stopped it: the product would pass 5 °C "
                f"in {breach:g} minutes and peak at {peak} °C"
                if not es else
                f"El chequeo físico lo frenó: el producto pasaría de 5 °C "
                f"en {breach:g} minutos y llegaría a {peak} °C"
            ),
            "payment_anomaly": (
                "A payment to a new bank account, for an unusual amount, "
                "at 2:02 in the morning"
                if not es else
                "Un pago a una cuenta bancaria nueva, por un monto inusual, "
                "a las 02:02 de la madrugada"
            ),
            "iban_then_payment": (
                "Acme Foods' bank details were changed and a payment "
                "followed seconds later"
                if not es else
                "Se cambiaron los datos bancarios de Acme Foods y segundos "
                "después siguió un pago"
            ),
            "token_burst": (
                "A burst of 12 calls in one minute with a single agent key"
                if not es else
                "Una ráfaga de 12 llamadas en un minuto con una sola llave "
                "de agente"
            ),
        }
        return texts.get(kind, "")

    def _timeline(self, incident, lang: str) -> list[dict[str, Any]]:
        es = lang == "es"
        by_kind: dict[str, list[str]] = {}
        for f in incident.findings:
            text = self._finding_texts(f.kind, es)
            if text:
                key = (
                    "payments"
                    if f.kind in ("payment_anomaly", "iban_then_payment")
                    else ("cold_room" if f.kind in ("defrost_anomaly", "physics_block")
                          else "ai_gateway")
                )
                by_kind.setdefault(key, []).append(text)
        rows = [
            ("cold_room",
             "Forced defrost hits the cold room (Europe 2 Nov pattern)" if not es
             else "Deshielo forzado contra la cámara (patrón Europa 2-nov)",
             "kept in last safe state" if not es else "quedó en su último estado seguro",
             FREEZER_SOURCES),
            ("payments",
             "A supplier's bank details are changed, then a payment follows (Arkéa pattern)"
             if not es else
             "Cambian los datos bancarios de un proveedor y sigue un pago (patrón Arkéa)",
             "transfer held, bank-details change frozen" if not es
             else "transferencia retenida, cambio de datos bancarios congelado",
             ARKEA_SOURCES),
            ("ai_gateway",
             "Calls burst in with a stolen agent key (our October incident)" if not es
             else "Llamadas en ráfaga con una llave de agente robada (nuestro incidente de octubre)",
             "key replaced: the attacker now gets 401" if not es
             else "llave reemplazada: el atacante ahora recibe 401",
             ()),
        ]
        return [
            {
                "app": app, "title": title, "findings": by_kind.get(app, []),
                "contained": contained, "sources": list(sources), "simulated": True,
            }
            for app, title, contained, sources in rows
        ]

    @staticmethod
    def _pending_business() -> dict[str, list[str]]:
        """Lo irreversible, en lenguaje de negocio y en los dos idiomas."""
        return {
            "en": [
                "Make Acme Foods' bank-details change final — only with your second factor",
                "Execute the held payment to Acme Foods — only with your second factor",
            ],
            "es": [
                "Dejar fijo el cambio de datos bancarios de Acme Foods: solo con tu segundo factor",
                "Ejecutar el pago retenido a Acme Foods: solo con tu segundo factor",
            ],
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
            "legit_still_running": self.legit_still_running,
            "still_breakdown": self.still_breakdown,
            "legit_total": 300,
            "scope_level": self.scope_level,
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
        "still_a": "Legitimate operations still running:",
        "still_b": "(shutting everything down: 0/300)",
        "still_why_global": "Why: three apps hit at once, so the engine went global and paused every AGENT write ({paused} of {total}); human payments to known suppliers keep going ({kept}).",
        "still_why_scoped": "Why: the engine froze only what the attack touched ({paused} of {total} paused).",
        "approve2fa": "Approve with 2nd factor",
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
        "still_a": "Operaciones legítimas que siguen vivas:",
        "still_b": "(apagar todo: 0/300)",
        "still_why_global": "Por qué: tres apps atacadas a la vez, así que el motor pasó a global y pausó toda escritura de AGENTES ({paused} de {total}); los pagos humanos a proveedores conocidos siguen ({kept}).",
        "still_why_scoped": "Por qué: el motor congeló solo lo que tocó el ataque ({paused} de {total} en pausa).",
        "approve2fa": "Aprobar con segundo factor",
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
.apps{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:12px 0}
.app-card{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:10px 16px}
.app-card h3{margin:0 0 4px;font-size:19px}.app-status{font-weight:700;font-size:14px}
.app-card[data-state="ok"] .app-status{color:var(--ok-text)}.app-card[data-state="contained"]{border-color:rgba(239,168,58,.65)}
.app-card[data-state="contained"] .app-status{color:var(--warn-text)}
.app-detail{color:var(--muted);font-size:14px;margin:4px 0 0}
.counter{text-align:center;margin:4px 0 2px}.counter b{font-size:50px;letter-spacing:-.02em;color:var(--warn-text)}
.counter span{display:block;color:var(--muted);font-size:15px}
.grid{display:grid;grid-template-columns:1.25fr .9fr;gap:14px;align-items:start;margin:10px 0}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:12px 18px}
.panel h2{margin:0 0 8px;font-size:20px}
.tl{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
.tl li{border:1px solid var(--line);border-radius:8px;padding:8px 12px;background:var(--sunk)}
.tl .t-head{display:flex;gap:10px;flex-wrap:wrap;align-items:baseline}.tl .t-title{font-weight:650;flex:1}
.tl .ms{font-family:var(--mono);color:var(--warn-text);font-size:14px}
.tl p{margin:4px 0;color:var(--muted);font-size:15px}
.chip{display:inline-flex;padding:2px 10px;border-radius:6px;font-size:13px;font-weight:700;background:rgba(239,168,58,.14);color:var(--warn-text);border:1px solid rgba(239,168,58,.5)}
.chip.allow{background:rgba(54,179,126,.14);color:var(--ok-text);border-color:rgba(54,179,126,.5)}
.chart{border:1px solid var(--line);border-radius:8px;overflow:hidden;margin-top:10px}
.chat{background:#0b3d2e;border:1px solid rgba(54,179,126,.5);border-radius:12px 12px 12px 2px;padding:12px 16px;max-width:560px}
.chat p{margin:5px 0;font-size:16px}.chat-text{font-size:17px;font-weight:650}
.stillrow{text-align:center;color:var(--muted);font-size:16px;margin:2px 0 8px}.stillrow b{color:var(--ok-text);font-size:19px}
.stillwhy{text-align:center;color:var(--muted);font-size:15px;margin:-4px auto 8px;max-width:1100px}
.chart svg{width:100%;height:auto;min-height:300px;max-height:340px}
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
  byId("stillN").textContent = (data.legit_still_running ?? 300) + "/" + (data.legit_total || 300);
  const sb = data.still_breakdown || {}; const why = byId("stillWhy");
  if (data.replayed && sb.scope_level === "global") {
    why.textContent = TEXT.still_why_global.replace("{paused}", sb.agent_writes_paused).replace("{kept}", sb.human_known_payments_kept).replace("{total}", sb.total);
    why.hidden = false;
  } else if (data.replayed && sb.scope_level) {
    why.textContent = TEXT.still_why_scoped.replace("{paused}", sb.agent_writes_paused).replace("{total}", sb.total);
    why.hidden = false;
  } else { why.hidden = true; }
  const tl = byId("timeline"); clear(tl);
  if (!data.replayed) { tl.appendChild(el("li", TEXT.not_run)); }
  (data.timeline || []).forEach((e2) => {
    const li = el("li");
    const head = el("div", null, "t-head");
    head.appendChild(el("span", e2.title, "t-title"));
    li.appendChild(head);
    (e2.findings || []).forEach((f) => li.appendChild(el("p", f)));
    const chip = el("span", TEXT.contained + " — " + e2.contained, "chip"); li.appendChild(chip);
    li.appendChild(el("span", " " + TEXT.simulated, "hint"));
    if ((e2.sources || []).length) { const p = el("p", TEXT.sources + ": "); e2.sources.forEach((u, i) => { const a = el("a", "[" + (i + 1) + "]"); a.href = u; a.target = "_blank"; a.rel = "noopener"; p.appendChild(a); p.appendChild(el("span", " ")); }); li.appendChild(p); }
    tl.appendChild(li);
  });
  const cold = byId("coldBody"); clear(cold);
  if (data.cold && data.cold.svg) {
    cold.appendChild(el("p", TEXT.kept_safe + " · setpoint " + data.cold.safe_setpoint_c + " °C · " + TEXT.peak + " " + data.cold.peak_product_c + " °C · " + TEXT.breach + " " + data.cold.predicted_breach_min));
    const chart = el("div", null, "chart"); chart.innerHTML = data.cold.svg; cold.appendChild(chart);
  } else { cold.appendChild(el("p", TEXT.not_run, "hint")); }
  const notice = byId("notice"); clear(notice);
  const noticeText = data.notice ? (TEXT.lang_code === "es" ? data.notice.text_es : data.notice.text_en) : "";
  if (noticeText) {
    noticeText.split("\n").forEach((line, i) => notice.appendChild(el("p", line, i === 0 ? "chat-text" : "")));
    // Una fila por medida de negocio («App: qué se hizo»); Undo deshace
    // todas las medidas del motor que caen bajo esa misma etiqueta.
    const byLabel = {};
    (data.measures || []).forEach((m) => { const k = TEXT.lang_code === "es" ? m.label_es : m.label_en; (byLabel[k] = byLabel[k] || []).push(m); });
    Object.entries(byLabel).forEach(([label, group]) => {
      const done = group.every((m) => m.undone);
      const row = el("div", null, "measure");
      row.appendChild(el("span", label));
      const b = el("button", done ? TEXT.undone : TEXT.undo, "btn small"); b.type = "button"; b.disabled = done;
      b.addEventListener("click", async () => { let last = null; for (const m of group) { if (m.undone) continue; const form = new FormData(); form.append("undo_id", m.undo_id); last = await api("/sentinel/undo", {method: "POST", body: form}); } if (last) render(last.data.state || last.data); });
      row.appendChild(b); notice.appendChild(row);
    });
    const pending = (data.pending_owner || {})[TEXT.lang_code] || [];
    pending.forEach((p) => notice.appendChild(el("p", "⏳ " + p, "hint")));
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
        f"<p class='stillrow'>{_e(t('still_a'))} <b id='stillN'>300/300</b> {_e(t('still_b'))}</p>"
        "<p class='stillwhy' id='stillWhy' hidden></p>"
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
        f"<button class='btn primary' id='releaseBtn' type='button'>{_e(t('approve2fa'))}</button>"
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
