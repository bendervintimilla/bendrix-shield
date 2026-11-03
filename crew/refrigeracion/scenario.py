"""Escenario de cadena de frío en replay: ataque, voz y rotación 401.

Sin red ni créditos: gateway FastAPI con ``MockTransport``, registro
en memoria y aprobación del dueño por el canal de voz existente
(``channels.voice.VoiceApprovalFlow`` sobre ``ApprovalBroker``).

Historia (la de los supermercados europeos de nov-2026, en un
restaurante):

1. Refrigeración trabaja normal: setpoint de cámara dentro de rango,
   en horario y desde el origen esperado -> ``allow`` y gateway 200.
2. Un token sin alcance de refrigeración (el de Bodega) intenta mover
   el setpoint -> ``block`` por alcance mínimo, sin mutar el equipo.
3. Atacante con el token **robado** de Refrigeración entra al gateway
   (200) e intenta subir la cámara a 15 °C y el congelador a 5 °C a
   las 03:00 desde otro país -> ``block`` con las tres señales
   (fuera de rango, fuera de horario, origen inesperado) y el equipo
   no se mueve.
4. El guardián propone rotar solo Refrigeración; el dueño confirma
   por voz («sí, rota refrigeración»); se rota ese token.
5. El atacante pasa a **401**; Refrigeración con su token nuevo,
   Bodega y Compras siguen en **200**; un cambio legítimo posterior
   se aplica.

Ningún token en claro sale del escenario: solo estados HTTP, motivos
y ``token_id`` públicos.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from channels.approvals import ApprovalBroker
from channels.voice import VoiceApprovalFlow
from crew.refrigeracion.agent import RefrigeracionAgent, SetpointRequest
from shield.actions import Actions
from shield.gateway.app import UPSTREAM_KEY_NAME, create_app
from shield.registry import Registry
from shield.sdk.token_store import LocalTokenStore
from shield.vault import MemoryVault

UPSTREAM_KEY = "upstream-real-key-cold-chain-replay"
MODEL = "muse-spark-1.3"
COLD_SCOPES = [
    "coldchain:read",
    "coldchain:setpoint:camara",
    "coldchain:setpoint:congelador",
]


def _ok_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["authorization"] == f"Bearer {UPSTREAM_KEY}"
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-cold",
            "model": MODEL,
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        },
    )


def _post(client: TestClient, raw: str, *, country: str | None = None) -> int:
    headers = {"Authorization": f"Bearer {raw}"}
    if country:
        headers["X-Demo-Country"] = country
    return client.post(
        "/v1/chat/completions",
        json={"model": MODEL, "messages": [{"role": "user", "content": "estado"}]},
        headers=headers,
    ).status_code


def run_scenario() -> dict[str, Any]:
    """Corre el escenario completo y devuelve el registro público."""
    started = time.perf_counter()
    steps: list[dict[str, Any]] = []
    registry = Registry(":memory:")
    app = create_app(
        registry=registry,
        vault=MemoryVault({UPSTREAM_KEY_NAME: UPSTREAM_KEY}),
        upstream_transport=httpx.MockTransport(_ok_handler),
        sandbox=True,
    )
    client = TestClient(app)
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalTokenStore(Path(tmp) / "agent-tokens.json")
        cold_meta, cold_raw = registry.create_token(
            "refrigeracion", "crew", scopes=COLD_SCOPES, models=[MODEL]
        )
        _, bodega_raw = registry.create_token("bodega", "crew", scopes=["crew"], models=[MODEL])
        _, compras_raw = registry.create_token("compras", "crew", scopes=["crew"], models=[MODEL])
        store.set_token("refrigeracion", cold_raw, cold_meta.token_id)

        device = RefrigeracionAgent(scopes=COLD_SCOPES)
        foreign = RefrigeracionAgent(scopes=["crew"], equipment=device.equipment)

        # 1) Trabajo legítimo.
        legit = device.request_setpoint(SetpointRequest("camara", 3.0, hour=10))
        legit_http = _post(client, cold_raw, country="EC")
        steps.append(
            {
                "step": "legit_setpoint",
                "evaluation": legit.public(),
                "gateway_status": legit_http,
            }
        )

        # 2) Alcance mínimo: otro agente no mueve el setpoint.
        denied = foreign.request_setpoint(SetpointRequest("camara", 3.5, hour=10))
        steps.append({"step": "foreign_token_scope", "evaluation": denied.public()})

        # 3) Atacante con el token robado: entra (200) e intenta el daño.
        attacker_before = _post(client, cold_raw, country="BR")
        attack_camara = device.request_setpoint(
            SetpointRequest("camara", 50.0, hour=3, origin_country="BR", origin="external")
        )
        attack_congelador = device.request_setpoint(
            SetpointRequest("congelador", 5.0, hour=3, origin_country="BR", origin="external")
        )
        steps.append(
            {
                "step": "stolen_token_attack",
                "gateway_status_before_rotation": attacker_before,
                "attacks": [attack_camara.public(), attack_congelador.public()],
                "equipment_after_attack": [e.public() for e in device.equipment.values()],
            }
        )

        # 4) Guardián + voz del dueño + rotación solo de Refrigeración.
        actions = Actions(registry=registry, token_store=store)
        broker = ApprovalBroker(registry=actions.approvals)
        plan = actions.rotate_token(grace_s=0).plan(agent="refrigeracion")
        # Sin la voz del dueño no hay rotación: el intento sin aprobación
        # falla y el token robado todavía responde 200 en ese instante.
        from shield.actions import ApprovalRequired

        unapproved_blocked = False
        try:
            actions.rotate_token(grace_s=0).apply(plan)
        except ApprovalRequired:
            unapproved_blocked = True
        steps.append(
            {
                "step": "rotation_without_owner_voice",
                "blocked_without_approval": unapproved_blocked,
                "attacker_status_at_that_moment": _post(client, cold_raw, country="BR"),
            }
        )
        req = broker.request(
            {
                "summary": "rotar token de refrigeracion por ataque a la cadena de frio",
                "steps": [
                    {
                        "action": "rotate_token",
                        "target": "refrigeracion",
                        "requires_approval": True,
                    }
                ],
            }
        )
        voice = VoiceApprovalFlow(broker).handle_transcript(
            req.approval_id, "sí, rota refrigeración"
        )
        result = actions.rotate_token(grace_s=0).apply(plan, approval_id=req.approval_id)
        steps.append(
            {
                "step": "owner_voice_rotation",
                "voice_status": voice.get("status"),
                "voice_intent": voice.get("intent"),
                "rotation_status": result.status,
                "rotated_agent": result.target,
                "new_token_id": result.new_token_id,
            }
        )

        # 5) Atacante 401; la cocina sigue en 200; cambio legítimo ok.
        attacker_after = _post(client, cold_raw, country="BR")
        cold_after = _post(client, store.get_token("refrigeracion") or "", country="EC")
        bodega_after = _post(client, bodega_raw, country="EC")
        compras_after = _post(client, compras_raw, country="EC")
        after = device.request_setpoint(SetpointRequest("congelador", -19.0, hour=11))
        steps.append(
            {
                "step": "after_rotation",
                "attacker_status": attacker_after,
                "refrigeracion_status": cold_after,
                "bodega_status": bodega_after,
                "compras_status": compras_after,
                "legit_setpoint": after.public(),
            }
        )

    elapsed = time.perf_counter() - started
    statuses = {
        "legit_gateway": steps[0]["gateway_status"],
        "attacker_before": attacker_before,
        "attacker_after": attacker_after,
        "refrigeracion_after": cold_after,
        "bodega_after": bodega_after,
        "compras_after": compras_after,
    }
    ok = (
        legit.decision == "allow"
        and legit.applied
        and denied.decision == "block"
        and attack_camara.decision == "block"
        and attack_congelador.decision == "block"
        and unapproved_blocked
        and voice.get("status") == "approved"
        and statuses["attacker_before"] == 200
        and statuses["attacker_after"] == 401
        and statuses["refrigeracion_after"] == 200
        and statuses["bodega_after"] == 200
        and statuses["compras_after"] == 200
        and after.applied
    )
    return {
        "scenario": "cold-chain-refrigeracion",
        "mode": "replay",
        "network": False,
        "credits_usd": 0,
        "ok": ok,
        "elapsed_s": round(elapsed, 3),
        "statuses": statuses,
        "attack_reasons": attack_camara.reasons,
        "final_equipment": [e.public() for e in device.equipment.values()],
        "steps": steps,
    }
