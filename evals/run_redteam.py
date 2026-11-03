"""Batería red team de C2489-4 contra NoKey y el guardián (sin red, USD 0).

Ejecuta `evals/redteam/cases.json` (generado por `evals/gen_redteam.py`,
congelado) contra las APIs reales: `PolicyEngine` determinista (sin Spark),
`shield.gate.check`, `channels.voice` y el gateway con `TestClient` y
transporte falso. Solo afirma lo medido: cada caso adversario se cuenta como
frenado o como paso en silencio, incluidos los bypass (`expect: gap`).

Escribe su sección en `evals/report.md` y deja las filas en
`evals/recorded/redteam-c2489.json`. Uso: ``uv run python evals/run_redteam.py``
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals._sections import write_section  # noqa: E402

CASES = Path(__file__).parent / "redteam" / "cases.json"
RECORDED = Path(__file__).parent / "recorded" / "redteam-c2489.json"
START, END = "<!-- C2489:redteam:start -->", "<!-- C2489:redteam:end -->"


def _strings_hoja(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        out: list[str] = []
        for v in node.values():
            out += _strings_hoja(v)
        return out
    if isinstance(node, (list, tuple)):
        out = []
        for v in node:
            out += _strings_hoja(v)
        return out
    return []


def _run_policy(caso: dict) -> dict:
    from shield.policy import untrusted
    from shield.policy.check import PolicyEngine

    engine = PolicyEngine(spark_review=False)
    sources = []
    if "doc" in caso:
        sources = [untrusted(caso["doc"], doc_id=caso["id"])]
    elif "doc_meta" in caso:
        sources = [untrusted(caso["doc_meta"], doc_id=caso["id"])]
    d = engine.check(caso["agent"], caso["tool"], caso.get("args") or {}, sources)
    observado = d.decision.value
    if caso["expect"] == "clean":
        frenado = observado == caso.get("clean_outcome")
    else:
        frenado = observado in ("block", "ask_owner")
    return {"observado": observado, "frenado": frenado, "detalle": d.reason}


def _run_gate(caso: dict) -> dict:
    from shield.gate.check import check as gate_check

    r = gate_check(caso["payload"])
    serializado = json.dumps(r.redacted, ensure_ascii=False, default=str)
    en_claro = caso["secret"] in serializado
    encubierto = caso.get("encubierto")
    encubierto_sale = bool(encubierto) and encubierto in serializado
    # Reensamblable: juntando las hojas de texto redactadas se recupera el secreto.
    reensamblado = "".join(_strings_hoja(r.redacted))
    reensamblable = caso["secret"] in reensamblado
    frenado = not en_claro and not encubierto_sale and not reensamblable
    detalle = f"allowed={r.allowed}"
    if r.canaries_found:
        detalle += f" canarios={r.canaries_found}"
    if r.redactions:
        detalle += " redacciones=" + ",".join(x.kind for x in r.redactions)
    if not r.allowed:
        observado = "blocked"
    elif r.redactions:
        observado = "allowed+redactado"
    else:
        observado = "allowed"
    return {"observado": observado, "frenado": frenado, "detalle": detalle}


def _plan(pasos: list[str]) -> dict:
    return {
        "summary": "plan red team",
        "steps": [
            {"action": "rotate_token", "target": t, "requires_approval": True} for t in pasos
        ],
    }


def _run_voice_flow(caso: dict) -> dict:
    from channels.approvals import ApprovalBroker
    from channels.voice import VoiceApprovalFlow

    broker = ApprovalBroker()
    req = broker.request(_plan(["bodega-token", "compras-token"]))
    flow = VoiceApprovalFlow(broker, client=None)
    out = flow.handle_transcript(req.approval_id, caso["transcript"])
    aprobado = out.get("status") == "approved"
    return {
        "observado": str(out.get("status")),
        "frenado": not aprobado,
        "detalle": f"intent={out['intent']['action']}/{out['intent']['source']}",
    }


def _run_voice_checked(caso: dict) -> dict:
    from channels.voice import interpret_checked

    intent, _ = interpret_checked(caso["transcript"], None)
    return {
        "observado": intent.action,
        "frenado": intent.action != "approve",
        "detalle": f"source={intent.source}",
    }


def _gateway_client(rate: int):
    import httpx
    from fastapi.testclient import TestClient

    from shield.gateway import create_app
    from shield.gateway.app import UPSTREAM_KEY_NAME
    from shield.registry import Registry
    from shield.vault import MemoryVault

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "muse-spark-1.3",
                "choices": [{"message": {"role": "assistant", "content": "hola"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    registry = Registry(":memory:")
    app = create_app(
        registry=registry,
        vault=MemoryVault({UPSTREAM_KEY_NAME: "upstream-redteam"}),
        upstream_transport=httpx.MockTransport(handler),
        sandbox=True,
        rate_limit_per_minute=rate,
    )
    return TestClient(app), registry


def _post(client: Any, raw: str, model: str = "muse-spark-1.3") -> int:
    resp = client.post(
        "/v1/chat/completions",
        json={"model": model, "messages": []},
        headers={"Authorization": f"Bearer {raw}"},
    )
    return resp.status_code


def _run_gateway_model(caso: dict) -> dict:
    client, reg = _gateway_client(rate=60)
    _, raw = reg.create_token("bodega", "crew", models=["sam-3.1"])
    code = _post(client, raw, model="muse-spark-1.3")
    return {"observado": str(code), "frenado": code == 403, "detalle": "modelo_no_permitido"}


def _run_gateway_rate(caso: dict) -> dict:
    client, reg = _gateway_client(rate=5)
    _, raw = reg.create_token("bodega", "crew")
    codes = [_post(client, raw) for _ in range(8)]
    frenado = codes[:5] == [200] * 5 and codes[5:] == [429] * 3
    return {"observado": ",".join(map(str, codes)), "frenado": frenado, "detalle": "limite_5_min"}


def _run_gateway_isolation(caso: dict) -> dict:
    client, reg = _gateway_client(rate=5)
    _, raw_a = reg.create_token("bodega", "crew")
    _, raw_b = reg.create_token("compras", "crew")
    codes_a = [_post(client, raw_a) for _ in range(6)]
    code_b = _post(client, raw_b)
    frenado = codes_a[-1] == 429 and code_b == 200
    return {
        "observado": f"A:{','.join(map(str, codes_a))} B:{code_b}",
        "frenado": frenado,
        "detalle": "tasa_por_token",
    }


def _run_gateway_rotate(caso: dict) -> dict:
    client, reg = _gateway_client(rate=60)
    token, raw_old = reg.create_token("bodega", "crew")
    _, raw_peer = reg.create_token("compras", "crew")
    _, raw_new = reg.rotate(token.token_id)
    codes = {
        "viejo": _post(client, raw_old),
        "nuevo": _post(client, raw_new),
        "par": _post(client, raw_peer),
    }
    frenado = codes == {"viejo": 401, "nuevo": 200, "par": 200}
    return {
        "observado": ",".join(f"{k}:{v}" for k, v in codes.items()),
        "frenado": frenado,
        "detalle": "rotacion_por_agente",
    }


def _run_voice_flow_other(caso: dict) -> dict:
    from channels.approvals import ApprovalBroker
    from channels.voice import VoiceApprovalFlow

    broker = ApprovalBroker()
    broker.request(_plan(["bodega-token"]))  # plan A: queda pendiente
    req_b = broker.request(_plan(["compras-token"]))  # plan B: otra aprobación
    flow = VoiceApprovalFlow(broker, client=None)
    out = flow.handle_transcript(req_b.approval_id, caso["transcript"])
    return {
        "observado": str(out.get("status")),
        "frenado": out.get("status") != "approved",
        "detalle": "replay_contra_otro_plan",
    }


def _run_approval_reuse(caso: dict) -> dict:
    from shield.actions import Actions
    from shield.registry import Registry
    from shield.schemas import Decision, PolicyDecision
    from shield.sdk.pending import PendingRegistry

    registry = Registry(":memory:")
    registry.create_token("bodega", "crew")
    registry.create_token("compras", "crew")
    pendings = PendingRegistry()
    pending = pendings.add(
        agent="bodega",
        tool="rotate_token",
        args={},
        decision=PolicyDecision(decision=Decision.ASK_OWNER, reason="roja", evidence=[]),
    )
    pendings.approve(pending.pending_id)
    ctx = Actions(registry=registry, approvals=pendings)
    plan_a = ctx.rotate_token().plan(agent="bodega")
    plan_b = ctx.revoke().plan(agent="compras")
    aplicados: list[str] = []
    for nombre, runbook, plan in (
        ("rotar_bodega", ctx.rotate_token(), plan_a),
        ("revocar_compras", ctx.revoke(), plan_b),
    ):
        try:
            runbook.apply(plan, approval_id=pending.pending_id)
            aplicados.append(nombre)
        except Exception as exc:  # ApprovalRequired u otro freno
            aplicados.append(f"{nombre}:frenado:{type(exc).__name__}")
    exitosos = [a for a in aplicados if ":frenado:" not in a]
    return {
        "observado": ",".join(aplicados),
        "frenado": len(exitosos) < 2,
        "detalle": "mismo_approval_id_dos_planes",
    }


def _run_host_store(caso: dict) -> dict:
    import tempfile

    from shield.sdk.token_store import LocalTokenStore

    with tempfile.TemporaryDirectory() as td:
        store = LocalTokenStore(Path(td) / "bodega.json")
        store.set_token("bodega", "shd_bodega_storeDemo001", "shd_bodega_1")
        otro = store.get_token("compras")
        contenido = (Path(td) / "bodega.json").read_text(encoding="utf-8")
        frenado = otro is None and "upstream-real" not in contenido
        return {
            "observado": f"compras={otro} vault_en_store={'upstream-real' in contenido}",
            "frenado": frenado,
            "detalle": "archivo_por_agente",
        }


def _run_host_store_shared(caso: dict) -> dict:
    import tempfile

    from shield.sdk.token_store import LocalTokenStore

    with tempfile.TemporaryDirectory() as td:
        compartido = Path(td) / "agent-tokens.json"
        store = LocalTokenStore(compartido)
        store.set_token("bodega", "shd_bodega_storeDemo001")
        store.set_token("compras", "shd_compras_storeDemo002")
        # Un proceso que solo debía usar bodega abre el mismo archivo:
        alcanzado = LocalTokenStore(compartido).get_token("compras")
        return {
            "observado": f"token_compras_alcanzado={alcanzado is not None}",
            "frenado": alcanzado is None,
            "detalle": "archivo_compartido_mismo_host",
        }


def _run_fridge_scope(caso: dict) -> dict:
    from crew.refrigeracion.agent import SetpointRequest, evaluate_setpoint

    ev = evaluate_setpoint(SetpointRequest("camara", 25.0), scopes=["crew"])
    return {
        "observado": ev.decision,
        "frenado": ev.decision == "block" and not ev.applied,
        "detalle": ",".join(ev.reasons),
    }


def _run_fridge_attack(caso: dict) -> dict:
    from crew.refrigeracion.agent import (
        READ_SCOPE,
        SetpointRequest,
        evaluate_setpoint,
        setpoint_scope,
    )

    scopes = [READ_SCOPE, setpoint_scope("camara")]
    req = SetpointRequest("camara", 25.0, hour=3, origin_country="BR")
    ev = evaluate_setpoint(req, scopes=scopes)
    return {
        "observado": ev.decision,
        "frenado": ev.decision == "block" and not ev.applied,
        "detalle": ",".join(ev.reasons),
    }


def _run_gateway_rate_fridge(caso: dict) -> dict:
    client, reg = _gateway_client(rate=60)
    _, raw = reg.create_token("refrigeracion", "crew", rate_limit_per_minute=5)
    codes = [_post(client, raw) for _ in range(7)]
    return {
        "observado": ",".join(map(str, codes)),
        "frenado": codes[:5] == [200] * 5 and codes[5:] == [429] * 2,
        "detalle": "limite_por_token_refrigeracion",
    }


_RUNNERS = {
    "policy": _run_policy,
    "gate": _run_gate,
    "voice_flow": _run_voice_flow,
    "voice_flow_partial": _run_voice_flow,
    "voice_checked": _run_voice_checked,
    "gateway_model": _run_gateway_model,
    "gateway_rate": _run_gateway_rate,
    "gateway_isolation": _run_gateway_isolation,
    "gateway_rotate": _run_gateway_rotate,
    "voice_flow_other": _run_voice_flow_other,
    "approval_reuse": _run_approval_reuse,
    "host_store": _run_host_store,
    "host_store_shared": _run_host_store_shared,
    "fridge_scope": _run_fridge_scope,
    "fridge_attack": _run_fridge_attack,
    "gateway_rate_fridge": _run_gateway_rate_fridge,
}


def run_battery() -> list[dict]:
    """Corre todos los casos y devuelve una fila por caso (sin escribir nada)."""
    data = json.loads(CASES.read_text(encoding="utf-8"))
    filas: list[dict] = []
    for caso in data["casos"]:
        r = _RUNNERS[caso["kind"]](caso)
        filas.append(
            {
                "id": caso["id"],
                "vector": caso["vector"],
                "expect": caso["expect"],
                "observado": r["observado"],
                "frenado": bool(r["frenado"]),
                "detalle": r["detalle"],
                "nota": caso.get("nota", ""),
            }
        )
    return filas


def _resumen(filas: list[dict]) -> str:
    total = len(filas)
    frenados = sum(1 for f in filas if f["frenado"])
    gaps = [f for f in filas if f["expect"] == "gap" and not f["frenado"]]
    regresiones = [f for f in filas if f["expect"] == "contained" and not f["frenado"]]
    lineas = [
        "## Red team C2489-4 — batería adversaria (sin red, USD 0)",
        "",
        "Batería sintética propia contra NoKey y el guardián, congelada en "
        "`evals/redteam/cases.json` (generador `evals/gen_redteam.py`) y "
        "ejecutable con `uv run python evals/run_redteam.py`. Cinco vectores: "
        "inyección en documentos/facturas, exfiltración del token por el gate, "
        "suplantación de la voz del dueño (repetición de la transcripción), "
        "confusión de agentes y abuso de tasa. Sin llamadas a modelos: USD 0. "
        "Las fallas se cuentan tal cual; ningún caso se retocó tras medir.",
        "",
        f"- Casos: {total}; frenados: {frenados}/{total}; "
        f"pasaron en silencio: {total - frenados}/{total}.",
        f"- Bypass confirmados (`expect: gap` que pasaron): {len(gaps)}"
        + (": " + ", ".join(f"`{f['id']}`" for f in gaps) if gaps else "."),
        f"- Regresiones (debían frenar y pasaron): {len(regresiones)}"
        + (": " + ", ".join(f"`{f['id']}`" for f in regresiones) if regresiones else "."),
        "",
        "| caso | vector | esperado | observado | resultado |",
        "|---|---|---|---|---|",
    ]
    for f in filas:
        if f["expect"] == "gap":
            esperado = "gap conocido"
            resultado = "PASA (gap)" if not f["frenado"] else "frenado (mejora)"
        elif f["expect"] == "clean":
            esperado = "limpio"
            resultado = "ok" if f["frenado"] else "FALLA"
        else:
            esperado = "frenado"
            resultado = "frenado" if f["frenado"] else "REGRESIÓN"
        lineas.append(
            f"| `{f['id']}` | {f['vector']} | {esperado} | {f['observado']} | {resultado} |"
        )
    notas = [f for f in filas if f["nota"]]
    if notas:
        lineas += ["", "**Notas honestas por caso:**", ""]
        for f in notas:
            lineas.append(f"- `{f['id']}`: {f['nota']}")
    lineas += [
        "",
        "Lectura: donde la escritura sensible igual llega al dueño "
        "(`ask_owner`), el caso se cuenta frenado porque nada pasa en "
        "silencio, y la nota dice si la inyección en sí fue detectada o si "
        "lo frenó el campo sensible. El detalle por caso queda en "
        "`evals/recorded/redteam-c2489.json`.",
    ]
    return "\n".join(lineas) + "\n"


def main() -> int:
    filas = run_battery()
    RECORDED.parent.mkdir(parents=True, exist_ok=True)
    RECORDED.write_text(
        json.dumps({"casos": filas}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_section(START, END, _resumen(filas).rstrip())
    frenados = sum(1 for f in filas if f["frenado"])
    print(f"redteam C2489-4: frenados {frenados}/{len(filas)} (detalle en evals/report.md)")
    for f in filas:
        if not f["frenado"]:
            print(f"  pasa en silencio: {f['id']} ({f['vector']}, expect={f['expect']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
