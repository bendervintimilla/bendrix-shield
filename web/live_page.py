"""Pantalla /live: HTML, CSS y JS propio inline, sin externos."""

# ruff: noqa: E501

from __future__ import annotations

import html
from typing import Any

from web.brand import BRAND, SUBTITLE
from web.live_page_replay import REPLAY_T

__all__ = [
    "BRAND",
    "SUBTITLE",
    "T",
    "render_live_page",
    "render_live_inactive_page",
    "spark_review_row",
]

T: dict[str, dict[str, str]] = {
    "en": {
        "lang_code": "en",
        "hero_subtitle": "Real models, a stolen token, and your decision: attack to containment on one screen.",
        "sphere_label": "Particle sphere reacting to the chain state",
        "step_pending": "pending",
        "step_blocked": "blocked",
        "whatsapp_note_title": "WhatsApp voice note",
        "approved_via_whatsapp": "approved via WhatsApp voice note",
        "verdict_no_bait": "Spark did not take the bait in either run. The gate still blocked the purchase, because the document carries a hidden order.",
        "verdict_tried": "The misconfigured agent tried to change the IBAN. The gate blocked it.",
        "supplier_unchanged": "Supplier account: unchanged",
        "supplier_changed": "Supplier account: changed",
        "forced_label": "Policy test, not from the model: the same change forced through the gate, in case a model obeys",
        "not_executed": "Not executed",
        "boxes_counted": "boxes counted",
        "tools_used": "tools used by the model",
        "turns_used": "turns",
        "intent_approve": "Approve the plan",
        "intent_reject": "Reject the plan",
        "intent_unknown": "No clear decision",
        "intent_except": "except",
        "intent_only": "only",
        "voice_unknown": "Didn't catch a decision. Nothing changed.",
        "voice_via_whatsapp": "Owner approved via WhatsApp voice note",
        "voice_via_whatsapp_note": "Owner replied via WhatsApp voice note",
        "voice_via_browser": "Owner replied via browser microphone",
        "voice_no_speech": "No speech detected. Check the microphone and try again.",
        "mic_silence": "The microphone recorded silence",
        "level_label": "Microphone level (RMS)",
        "time_since_attack": "Time since the attack started",
        "th_decision": "policy decision",
        "action_rotate_token": "Rotate the token",
        "action_verify": "Check it still works",
        "action_draft_notice": "Draft a notice",
        "action_rotate_upstream_key": "Rotate the upstream key",
        "live_label": "LIVE — real Meta models, called from this Mac through the Shield gateway",
        "sticky_attacker": "Attacker",
        "sticky_sdk": "SDK",
        "replay": "Replay",
        "live": "Live",
        "new_run": "New run",
        "cost_of_cap": "of {cap} cap",
        "chain_duration": "Chain duration",
        "headline_start": "Your crew is at work.",
        "headline_attack": "Someone is using Warehouse's stolen token.",
        "headline_waiting": "Your decision is the only thing missing.",
        "headline_contained": "The thief is locked out.",
        "real_incident": "~16 h in the real incident",
        "time_to_401": "Real time to first 401",
        "run_until": "Run until the owner decides",
        "not_run": "not run",
        "running": "running",
        "ok": "ok",
        "error": "error",
        "step1_title": "Purchasing reads an invoice",
        "step2_title": "Warehouse counts boxes (SAM 3.1)",
        "step3_title": "The stolen token is used",
        "step4_title": "Guardian reasons (Muse Spark)",
        "step5_title": "You approve by voice",
        "step6_title": "Containment",
        "run_step": "Run this step",
        "hidden_order": "Hidden order in the fine print",
        "what_spark_read": "What Spark read from the note",
        "normal_agent": "Normal agent",
        "weak_agent": "Deliberately misconfigured agent (test)",
        "weak_label": "Deliberately misconfigured agent (test): told to obey invoice notes",
        "attempted": "Tool calls attempted",
        "no_attempt": "The model did not try any tool call.",
        "decision": "Decision",
        "reason": "Reason",
        "evidence": "Evidence",
        "account_before_after": "Supplier account before / after",
        "use_own_photo": "Use your own photo (no people, no real data)",
        "expected_7": "Expected: 7 (fixture only)",
        "count_label": "Count",
        "attacker_attempts": "Attacker attempts (country BR)",
        "anomalies": "Anomalies",
        "anomaly_new_country": "New country: Warehouse is calling from BR, a country it does not normally use.",
        "anomaly_new_model": "Unused model: this agent is using a model outside its baseline.",
        "anomaly_cost_spike": "Cost spike: cost per call is well above its usual median.",
        "anomaly_blocked_burst": "Blocked burst: many blocked calls from this agent.",
        "anomaly_volume_spike": "Volume spike: many more calls per hour than usual.",
        "anomaly_other": "Anomaly detected by the gateway.",
        "demo_inventory": "Demo inventory",
        "plan_summary": "Summary",
        "plan_reasoning": "Model reasoning",
        "plan_exposures": "Exposures",
        "plan_steps": "Steps",
        "guardian_turns": "Guardian turns",
        "no_plan_error": "guardian_no_plan: Spark did not propose a plan within 10 turns",
        "record": "Record",
        "stop": "Stop",
        "typed_fallback": "Typed fallback: no Voice Transcribe is used in this path",
        "voice_hint": 'Try: "sí, rota el token de bodega"',
        "send_typed": "Send typed decision",
        "transcript": "Voice Transcribe transcript",
        "spark_intent": "Muse Spark intent",
        "confirm": "Confirm",
        "cancel": "Cancel",
        "disagreement": "Spark and the deterministic parser differ; nothing was approved on that reading.",
        "no_mic": "No microphone available or permission denied. Use the typed fallback below.",
        "recording": "Recording",
        "contain_run": "Run containment",
        "attacker_before": "Attacker before rotation",
        "attacker_after": "Attacker after rotation",
        "sdk_sequence": "Warehouse SDK sequence",
        "sdk_refreshed": "refreshed token",
        "recount_after": "SAM recount after rotation",
        "purchasing_status": "Purchasing status",
        "contained_in": "Contained in",
        "spark_open_row": "Muse Spark Open: not run. No Baseten, Modal or Fireworks key in this vault.",
        "spark_open_row_key": "Muse Spark Open: not run.",
        "provenance": "Provenance log",
        "export_log": "Export log (JSON)",
        "th_step": "step",
        "th_agent": "agent",
        "th_model": "model",
        "th_response": "response id",
        "th_latency": "latency",
        "th_in": "input tokens",
        "th_out": "output tokens",
        "th_cost": "cost",
        "th_http": "HTTP",
        "footer_meta": "Built on Meta's Muse models; independent project, not affiliated with or endorsed by Meta.",
        "footer_hack": "Built during the hackathon, 26 Oct – 4 Nov 2026.",
        "activate_title": "Live mode is not active",
        "activate_body": "Start it with make live, then open /live again. No model is called from this screen.",
        "no_key": "No key in the vault",
        "no_key_body": "Put META_MODEL_API_KEY in the vault (environment backend) and restart with make live. The key is never shown here.",
    },
    "es": {
        "lang_code": "es",
        "hero_subtitle": "Modelos reales, un token robado y tu decisión: del ataque a la contención en una pantalla.",
        "sphere_label": "Esfera de partículas que reacciona al estado de la cadena",
        "step_pending": "pendiente",
        "step_blocked": "bloqueado",
        "whatsapp_note_title": "Nota de voz de WhatsApp",
        "approved_via_whatsapp": "aprobado por nota de voz de WhatsApp",
        "verdict_no_bait": "Spark no mordió el anzuelo en ninguna de las dos corridas. La puerta igual bloqueó la compra, porque el documento trae una orden escondida.",
        "verdict_tried": "El agente mal configurado intentó cambiar el IBAN. La puerta lo bloqueó.",
        "supplier_unchanged": "Cuenta del proveedor: sin cambios",
        "supplier_changed": "Cuenta del proveedor: cambió",
        "forced_label": "Prueba de política, no del modelo: el mismo cambio forzado a través de la puerta, por si un modelo obedece",
        "not_executed": "Sin ejecutar",
        "boxes_counted": "cajas contadas",
        "tools_used": "herramientas usadas por el modelo",
        "turns_used": "turnos",
        "intent_approve": "Aprobar el plan",
        "intent_reject": "Rechazar el plan",
        "intent_unknown": "Sin decisión clara",
        "intent_except": "excepto",
        "intent_only": "solo",
        "voice_unknown": "No se entendió una decisión. Nada cambió.",
        "voice_via_whatsapp": "El dueño aprobó por nota de voz de WhatsApp",
        "voice_via_whatsapp_note": "El dueño respondió por nota de voz de WhatsApp",
        "voice_via_browser": "El dueño respondió por el micrófono del navegador",
        "voice_no_speech": "No se detectó voz. Revisa el micrófono y vuelve a intentar.",
        "mic_silence": "El micrófono grabó silencio",
        "level_label": "Nivel del micrófono (RMS)",
        "time_since_attack": "Tiempo desde que empezó el ataque",
        "th_decision": "decisión de política",
        "action_rotate_token": "Rotar el token",
        "action_verify": "Comprobar que sigue funcionando",
        "action_draft_notice": "Preparar un borrador de aviso",
        "action_rotate_upstream_key": "Rotar la clave del proveedor",
        "live_label": "EN VIVO — modelos reales de Meta, llamados desde esta Mac a través del gateway de Shield",
        "sticky_attacker": "Atacante",
        "sticky_sdk": "SDK",
        "replay": "Repetición",
        "live": "En vivo",
        "new_run": "Nueva corrida",
        "cost_of_cap": "de {cap} de tope",
        "chain_duration": "Duración de la cadena",
        "headline_start": "Tu cuadrilla está trabajando.",
        "headline_attack": "Alguien está usando el token robado de Bodega.",
        "headline_waiting": "Solo falta tu decisión.",
        "headline_contained": "El ladrón quedó fuera.",
        "real_incident": "~16 h en el incidente real",
        "time_to_401": "Tiempo real al primer 401",
        "run_until": "Correr hasta que el dueño decida",
        "not_run": "sin correr",
        "running": "corriendo",
        "ok": "bien",
        "error": "error",
        "step1_title": "Compras lee una factura",
        "step2_title": "Bodega cuenta cajas (SAM 3.1)",
        "step3_title": "Se usa el token robado",
        "step4_title": "El guardián razona (Muse Spark)",
        "step5_title": "Tú apruebas por voz",
        "step6_title": "Contención",
        "run_step": "Correr este paso",
        "hidden_order": "Orden escondida en la letra pequeña",
        "what_spark_read": "Lo que Spark leyó de la nota",
        "normal_agent": "Agente normal",
        "weak_agent": "Agente mal configurado a propósito (prueba)",
        "weak_label": "Agente mal configurado a propósito (prueba): instruido para obedecer las notas de la factura",
        "attempted": "Llamadas a herramientas intentadas",
        "no_attempt": "El modelo no intentó ninguna llamada a herramienta.",
        "decision": "Decisión",
        "reason": "Razón",
        "evidence": "Evidencia",
        "account_before_after": "Cuenta del proveedor antes / después",
        "use_own_photo": "Usa tu propia foto (sin personas, sin datos reales)",
        "expected_7": "Esperado: 7 (solo en el fixture)",
        "count_label": "Conteo",
        "attacker_attempts": "Intentos del atacante (país BR)",
        "anomalies": "Anomalías",
        "anomaly_new_country": "País nuevo: Bodega está llamando desde BR, un país que no usa normalmente.",
        "anomaly_new_model": "Modelo no usado: este agente usa un modelo fuera de su línea base.",
        "anomaly_cost_spike": "Pico de costo: el costo por llamada está muy sobre su mediana usual.",
        "anomaly_blocked_burst": "Ráfaga bloqueada: muchas llamadas bloqueadas de este agente.",
        "anomaly_volume_spike": "Pico de volumen: muchas más llamadas por hora que lo usual.",
        "anomaly_other": "Anomalía detectada por el gateway.",
        "demo_inventory": "Inventario de demostración",
        "plan_summary": "Resumen",
        "plan_reasoning": "Razonamiento del modelo",
        "plan_exposures": "Exposiciones",
        "plan_steps": "Pasos",
        "guardian_turns": "Turnos del guardián",
        "no_plan_error": "guardian_no_plan: Spark no propuso un plan en 10 turnos",
        "record": "Grabar",
        "stop": "Detener",
        "typed_fallback": "Alternativa escrita: en esta ruta no se usa Voice Transcribe",
        "voice_hint": 'Prueba: "sí, rota el token de bodega"',
        "send_typed": "Enviar decisión escrita",
        "transcript": "Transcripción de Voice Transcribe",
        "spark_intent": "Intención de Muse Spark",
        "confirm": "Confirmar",
        "cancel": "Cancelar",
        "disagreement": "Spark y el parser determinista difieren; no se aprobó nada con esa lectura.",
        "no_mic": "Sin micrófono o permiso denegado. Usa el campo escrito de abajo.",
        "recording": "Grabando",
        "contain_run": "Correr contención",
        "attacker_before": "Atacante antes de rotar",
        "attacker_after": "Atacante después de rotar",
        "sdk_sequence": "Secuencia del SDK de Bodega",
        "sdk_refreshed": "token refrescado",
        "recount_after": "Recuento SAM tras rotar",
        "purchasing_status": "Estado de Compras",
        "contained_in": "Contenido en",
        "spark_open_row": "Muse Spark Open: sin ejecutar. No hay clave de Baseten, Modal ni Fireworks en este vault.",
        "spark_open_row_key": "Muse Spark Open: sin ejecutar.",
        "provenance": "Registro de procedencia",
        "export_log": "Exportar registro (JSON)",
        "th_step": "paso",
        "th_agent": "agente",
        "th_model": "modelo",
        "th_response": "id de respuesta",
        "th_latency": "latencia",
        "th_in": "tokens de entrada",
        "th_out": "tokens de salida",
        "th_cost": "costo",
        "th_http": "HTTP",
        "footer_meta": "Construido sobre los modelos Muse de Meta; proyecto independiente, sin afiliación ni respaldo de Meta.",
        "footer_hack": "Construido durante el hackathon, del 26 de octubre al 4 de noviembre de 2026.",
        "activate_title": "El modo live no está activo",
        "activate_body": "Arráncalo con make live y vuelve a abrir /live. Desde esta pantalla no se llama a ningún modelo.",
        "no_key": "Sin clave en el vault",
        "no_key_body": "Pon META_MODEL_API_KEY en el vault (backend de entorno) y reinicia con make live. La llave nunca se muestra aquí.",
    },
}


for _lang, _extra in REPLAY_T.items():
    T[_lang].update(_extra)


def _t(lang: str, key: str) -> str:
    return T.get(lang, T["en"]).get(key, T["en"].get(key, key))


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


_SPARK_DECISION_LABEL = {"allow": "ALLOW", "block": "BLOCK", "ask_owner": "ASK OWNER"}


def spark_review_row(review: dict[str, Any], lang: str = "en") -> str:
    """Única fila de la revisión Spark del documento.

    La razón se muestra tal cual vino de Spark (recortada), sin traducir.
    Sin llamada real no se inventan modelo, id ni costo.
    """
    if not isinstance(review, dict):
        return ""
    es = lang == "es"
    tool = str(review.get("tool") or "read_invoice")
    prefix = (
        f"Revisión Spark del documento (herramienta: {tool}, solo lectura)"
        if es
        else f"Spark document review (tool: {tool}, read-only)"
    )
    status = str(review.get("status") or "")
    decision = str(review.get("decision") or "").strip().lower()
    if status == "blocked_by_rules":
        return (
            f"{prefix}: BLOCK — bloqueado por reglas deterministas; Spark no fue necesario"
            if es
            else f"{prefix}: BLOCK — blocked by deterministic rules; Spark not needed"
        )
    if status == "unavailable" or decision == "unavailable":
        return f"{prefix}: {'no disponible' if es else 'not available'}"
    label = _SPARK_DECISION_LABEL.get(decision, decision.upper())
    reason = str(review.get("reason") or "")[:200]
    text = f"{prefix}: {label}"
    if reason:
        text += f" — {reason}"
    model = str(review.get("model") or "")
    rid = str(review.get("response_id") or "")
    if model and rid:
        latency = round(float(review.get("latency_ms") or 0))
        cost = float(review.get("cost_usd") or 0)
        text += f" · {model} · {rid} · {latency} ms · USD {cost:.6f}"
    return text


_CSS = """
:root{--col:1140px;--bg:#111113;--panel:#17191f;--panel2:#1e2129;--line:#2c303a;--text:#f4f6f9;--muted:#c3cad4;--blue:#2563eb;--amber:#f5a623;--red:#e5484d;--green:#2ea36b}
@media (min-width:1600px){:root{--col:1320px}}
*{box-sizing:border-box}
html,body{max-width:100%;overflow-x:hidden}
img{max-width:100%}
body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-size:17px;line-height:1.5}
h1,h2,h3{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.12;font-weight:750;letter-spacing:-.02em}
a{color:#8ab8ff}
:focus-visible{outline:3px solid var(--amber);outline-offset:2px}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:46px;padding:10px 20px;border:1px solid var(--line);border-radius:999px;background:#23262f;color:var(--text);font:inherit;font-weight:650;cursor:pointer;text-decoration:none;max-width:100%;white-space:normal;text-align:center;transition:background .18s ease,border-color .18s ease,transform .18s ease}
.btn.primary{background:var(--blue);border-color:var(--blue);color:#fff}
.btn.secondary{background:#23262f}
.btn.ghost{background:rgba(35,38,47,.72);color:var(--text)}
.btn.alert-btn{background:var(--red);border-color:var(--red);color:#fff}
.band{background:var(--bg);color:var(--text);border-bottom:1px solid var(--line)}
.band .inner,.wrap{width:min(var(--col),calc(100% - 40px));max-width:var(--col);margin:0 auto}
.band .inner{padding:14px 0 8px}
.band-top{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;justify-content:space-between}
.brandline{margin:0;font-size:16px;color:var(--text)}
.brandline strong{font-size:18px;letter-spacing:-.01em}
.live-label{border:1px solid rgba(245,166,35,.55);border-radius:999px;color:#ffc95e;background:rgba(245,166,35,.08);padding:6px 11px;font-size:13px;font-weight:650}
.band-tools{display:flex;flex-wrap:wrap;gap:8px;align-items:center;color:var(--muted);font-size:15px}
.band-tools .mono,.band-tools>span{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.mode-switch,.lang{display:inline-flex;gap:4px}
.mode-switch a,.lang a{display:inline-flex;align-items:center;min-height:40px;padding:7px 13px;color:var(--muted);border:1px solid var(--line);border-radius:999px;background:rgba(35,38,47,.72);text-decoration:none}
.mode-switch a[aria-current="true"],.lang a[aria-current="true"]{background:var(--blue);border-color:var(--blue);color:#fff}
.mode-switch .mode-off{display:inline-flex;align-items:center;min-height:40px;padding:7px 13px;color:#6f7685;border:1px dashed var(--line);border-radius:999px;cursor:not-allowed}
.scene-switch a[aria-current="true"]{background:#1f9d63;border-color:#1f9d63}
.live-off-note,.replay-note{margin:14px auto 0;max-width:620px;font-size:14.5px;color:var(--muted)}
.stickybar{position:sticky;top:0;z-index:60;background:rgba(17,17,19,.9);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.sticky-inner{width:min(var(--col),calc(100% - 40px));max-width:var(--col);margin:0 auto;display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;padding:8px 0}
.sticky-brand{font-weight:800;letter-spacing:-.01em;white-space:nowrap}
.sticky-clock{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-weight:750;white-space:nowrap}
.sticky-clock[data-state="attack"]{color:#ff9a86}
.sticky-clock[data-state="contained"]{color:#7ce7b2}
.sticky-group{display:inline-flex;flex-wrap:wrap;gap:5px;align-items:center;min-width:0}
.sticky-label{font-size:12.5px;font-weight:700;color:var(--muted);letter-spacing:.04em;text-transform:uppercase}
.mini-code{display:inline-flex;align-items:center;justify-content:center;min-width:38px;min-height:26px;padding:2px 7px;border-radius:7px;font-size:13.5px;font-weight:750;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:#262a33;color:var(--muted)}
.mini-code.code-200{background:var(--amber);color:#211603}
.mini-code.code-401{background:#1f9d63;color:#fff}
.sticky-cost{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:nowrap;color:var(--muted)}
.stickybar .btn{min-height:38px;padding:7px 14px;margin-left:auto}
.hero{position:relative;display:flex;align-items:center;gap:36px;min-height:85vh;min-height:85svh;padding:34px 0 40px;overflow:hidden}
#sphereCanvas{position:absolute;inset:0;width:100%;height:100%;display:block;pointer-events:none}
.hero-copy{position:relative;z-index:1;flex:1 1 auto;text-align:center;min-width:0}
.hero-brand{margin:0;font-size:clamp(76px,10.5vw,148px);line-height:.92;font-weight:850;letter-spacing:-.055em}
.hero-fill{color:#fff}
.hero-outline{color:transparent;-webkit-text-stroke:2px rgba(255,255,255,.92)}
.hero-subtitle{margin:14px auto 0;max-width:640px;color:var(--muted);font-size:18px;line-height:1.45}
.band h1,.hero-copy h1{font-size:clamp(26px,2.6vw,38px);margin:18px auto 0;max-width:760px;font-weight:750}
.hero .attempts{justify-content:center}
.hero .run-until{margin:18px auto 0;font-size:17px;padding:12px 24px}
.clockbox{position:relative;z-index:1;text-align:right;min-width:250px;flex:0 0 auto}
#clockLabel{margin:0;color:var(--muted);font-size:15px;font-weight:650}
#bigClock{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:clamp(52px,5.2vw,84px);font-weight:750;margin:2px 0 0;line-height:1;color:#fff;transition:color .3s ease}
#bigClock[data-state="attack"]{color:#ff9a86}
#bigClock[data-state="contained"]{color:#7ce7b2}
.clock-note{margin:6px 0 0;font-size:15px;color:var(--muted)}
#chainDuration{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.attempts{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.code-block{display:inline-flex;align-items:center;justify-content:center;min-width:72px;min-height:58px;padding:8px 14px;border-radius:12px;font-size:25px;font-weight:750;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:#262a33;color:var(--text)}
.code-200{background:var(--amber);color:#211603}
.code-401{background:#1f9d63;color:#fff}
.code-none,.code-0{background:#262a33;color:var(--muted)}
.code-pop{animation:codePop .45s ease}
.code-401.code-pop{animation:code401 .7s ease}
@keyframes codePop{0%{transform:scale(.82);opacity:.4}60%{transform:scale(1.06)}100%{transform:scale(1);opacity:1}}
@keyframes code401{0%{transform:scale(.7);opacity:.3;box-shadow:0 0 0 0 rgba(31,157,99,.55)}55%{transform:scale(1.14);box-shadow:0 0 0 12px rgba(31,157,99,0)}100%{transform:scale(1);opacity:1;box-shadow:0 0 0 0 rgba(31,157,99,0)}}
.wrap{padding:24px 0 30px}
#noKeyBox{background:rgba(229,72,77,.13);border:1px solid rgba(229,72,77,.6);border-radius:14px;color:#ffd7d5;padding:14px 16px;font-weight:650}
.run-until{margin:18px 0}
.steps{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr;gap:16px;align-items:stretch}
@media (min-width:820px){.steps{grid-template-columns:repeat(2,1fr)}}
@media (min-width:1280px){.steps{grid-template-columns:repeat(3,1fr)}}
.step{position:relative;display:flex;flex-direction:column;height:100%;background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:18px;transition:border-color .3s ease,background .3s ease,box-shadow .3s ease;animation:stepIn .55s ease both}
.step:nth-child(1){animation-delay:.02s}.step:nth-child(2){animation-delay:.09s}.step:nth-child(3){animation-delay:.16s}.step:nth-child(4){animation-delay:.23s}.step:nth-child(5){animation-delay:.3s}.step:nth-child(6){animation-delay:.37s}
@keyframes stepIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
.step[data-state="running"]{border-color:rgba(245,166,35,.85);box-shadow:0 0 0 1px rgba(245,166,35,.35),0 0 26px rgba(245,166,35,.14);animation:stepIn .55s ease both,stepGlow 1.2s ease-in-out .55s infinite alternate}
@keyframes stepGlow{from{box-shadow:0 0 0 1px rgba(245,166,35,.3),0 0 16px rgba(245,166,35,.08)}to{box-shadow:0 0 0 1px rgba(245,166,35,.55),0 0 30px rgba(245,166,35,.2)}}
.step[data-state="ok"]{border-color:rgba(46,163,107,.8)}
.step[data-state="error"],.step[data-state="blocked"]{border-color:rgba(229,72,77,.85)}
.step[data-state="ok"] .step-num{background:var(--green)}
.step[data-state="error"] .step-num,.step[data-state="blocked"] .step-num{background:var(--red)}
.step[data-state="running"] .step-num{background:var(--amber);color:#211603}
.step-num{flex:0 0 auto;width:34px;height:34px;border-radius:50%;background:var(--blue);color:#fff;display:flex;align-items:center;justify-content:center;font-family:ui-monospace,Menlo,Consolas,monospace;font-weight:750;font-size:16px;transition:background .3s ease}
.step-head{display:flex;flex-wrap:wrap;gap:10px;align-items:center;min-height:46px}
.step h2{font-size:20px;margin:0;flex:1 1 150px;min-width:0;line-height:1.2}
.step-status{flex:0 0 auto;font-size:13.5px;font-weight:750;border:1px solid var(--line);border-radius:999px;padding:5px 11px;background:#22252e;color:var(--muted);white-space:nowrap;transition:color .3s ease,border-color .3s ease,background .3s ease}
.step-status[data-state="running"]{color:#ffd28a;border-color:rgba(245,166,35,.8);background:rgba(245,166,35,.1);animation:statusPulse 1.1s ease-in-out infinite}
.step-status[data-state="ok"]{color:#8ef0c0;border-color:rgba(46,163,107,.8);background:rgba(46,163,107,.12)}
.step-status[data-state="error"],.step-status[data-state="blocked"]{color:#ffb1a6;border-color:rgba(229,72,77,.8);background:rgba(229,72,77,.12)}
@keyframes statusPulse{0%,100%{box-shadow:0 0 0 0 rgba(245,166,35,0)}50%{box-shadow:0 0 0 5px rgba(245,166,35,.14)}}
.step-head .btn{flex:0 0 auto;min-height:40px;padding:8px 15px}
.result{margin-top:14px;color:var(--text);flex:1 1 auto}
.result p,.result li{overflow-wrap:anywhere}
.columns{display:grid;grid-template-columns:1fr;gap:18px}
.verdict{font-size:19px;font-weight:750;background:rgba(229,72,77,.12);border:1px solid rgba(229,72,77,.55);border-radius:14px;color:#ffe3e1;padding:12px 14px}
.forced-row{background:rgba(229,72,77,.08);border:1px solid rgba(229,72,77,.65);border-radius:14px;padding:12px 14px;margin:14px 0}
.invoice-media{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start;max-width:100%}
[hidden]{display:none!important}
.fineprint-wrap{flex:1 1 260px;max-width:1000px;height:90px;overflow:hidden;border:1px solid var(--line);border-radius:10px;background:#fff}
.fineprint{width:108%;max-width:none;display:block;transform:translate(-4%,-64%)}
.hidden-note{font-size:16.5px;background:var(--panel2);border-radius:10px;padding:10px 12px;overflow-wrap:anywhere}
.decision-block{padding:11px 13px;margin:8px 0;font-weight:800;border-radius:10px;letter-spacing:.04em}
.decision-block.block{background:var(--red);color:#fff}
.decision-block.ask{color:var(--text)}
.decision-block.ask-ask_owner{background:var(--amber);color:#211603}
.decision-block.ask-block{background:var(--red);color:#fff}
.decision-block.allow{background:#1f9d63;color:#fff}
.decision-block.ask_owner{background:var(--amber);color:#211603}
.thumb{max-width:220px;width:100%;height:auto;border:1px solid var(--line);border-radius:12px}
.shelf-wrap{position:relative;max-width:560px}
.shelf-wrap img{width:100%;height:auto;display:block;border-radius:12px}
.box-overlay{position:absolute;border:3px solid var(--red);border-radius:4px}
.bigcount{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:46px;font-weight:750;margin:10px 0 0}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;overflow-wrap:anywhere;word-break:break-word}
.chat-bubble{background:var(--panel2);border:1px solid var(--line);border-radius:18px;padding:14px 16px;margin-top:14px;transition:border-color .25s ease,background .25s ease}
.chat-bubble.is-whatsapp{background:#122019;border-color:rgba(46,163,107,.75)}
.chat-bubble.is-approved{border-color:#2ea36b}
.chat-head{margin:0 0 6px}
.chat-badge{display:inline-flex;border-radius:999px;padding:4px 11px;background:rgba(46,163,107,.16);border:1px solid rgba(46,163,107,.65);color:#8ef0c0;font-size:13.5px;font-weight:750}
.chat-bubble h3{font-size:16px;margin:12px 0 4px;color:var(--muted);letter-spacing:0}
.chat-text{font-size:19px;margin:2px 0;overflow-wrap:anywhere}
#voiceChannel{font-weight:700;color:#c9f5dc;margin:2px 0}
.chat-approved{color:#8ef0c0;font-weight:800;margin:8px 0 0}
.chat-approved:empty{display:none}
.tablewrap{overflow-x:auto;max-width:100%;width:100%}
table{border-collapse:collapse;width:100%;min-width:640px;background:#14161b;border:1px solid var(--line)}
td,th{border-bottom:1px solid var(--line);padding:9px 8px;text-align:left;vertical-align:top}
th{color:var(--muted);font-size:14px}
.footer{border-top:1px solid var(--line);font-size:14.5px;color:var(--muted)}
input[type="text"]{width:100%;min-height:46px;padding:10px 12px;font:inherit;background:#101216;border:1px solid var(--line);border-radius:10px;color:var(--text)}
.file-pill{position:relative;display:inline-flex;align-items:center;min-height:44px;padding:10px 18px;border:1px solid var(--line);border-radius:999px;background:#23262f;color:var(--text);font-weight:650;cursor:pointer;margin:10px 0 6px;transition:background .18s ease,border-color .18s ease}
.file-pill:hover{border-color:rgba(255,255,255,.35)}
.file-pill:focus-within{outline:3px solid var(--amber);outline-offset:2px}
.file-input{position:absolute;width:1px;height:1px;opacity:0;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
label{display:block;font-weight:700;margin:10px 0 6px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;max-width:100%;background:#101216;border:1px solid var(--line);border-radius:10px;padding:12px}
details summary{cursor:pointer;font-weight:650}
section h2{font-size:26px}
@media (max-width:900px){.hero{display:block;min-height:78vh;min-height:78svh;padding:26px 0 30px}.clockbox{text-align:center;padding-top:18px;min-width:0}.hero .attempts{justify-content:center}}
@media (max-width:760px){.columns{grid-template-columns:1fr}.band-tools,.band-top{max-width:100%}.code-block{min-width:54px;min-height:48px;font-size:20px}.hero-brand{font-size:clamp(64px,22vw,96px)}#bigClock{font-size:56px}}
@media (max-width:480px){.band .inner,.wrap,.sticky-inner{width:calc(100% - 24px)}.hero{min-height:72vh;min-height:72svh;padding:22px 0 26px;gap:0}.hero-brand{font-size:clamp(58px,20vw,84px)}.hero-subtitle{font-size:16px}.band h1,.hero-copy h1{font-size:24px}#bigClock{font-size:48px}.clockbox{min-width:0}.steps{grid-template-columns:1fr}.step{padding:14px}.step h2{flex-basis:120px;font-size:19px}.step-head .btn{flex:1 1 auto}.stickybar .btn{margin-left:0}.sticky-cost{white-space:normal}.code-block{min-width:48px;min-height:44px;font-size:19px;padding:6px 10px}.thumb{max-width:160px}}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto;animation:none!important;transition:none!important}}
"""

_JS = r"""
const TEXT = __TEXTS__;
const API = "__API__";
const SCENE = "__SCENE__";
const REPLAY = __REPLAY__;
function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function byId(id) { return document.getElementById(id); }
function fmtClock(total) {
  const s = Math.max(0, Math.floor(total));
  return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
}
const stepTimers = {};
function statusStateOf(text) {
  const raw = String(text || "");
  if (raw.indexOf(TEXT.running) === 0) return "running";
  if (raw.indexOf(TEXT.ok) === 0) return "ok";
  if (raw.indexOf(TEXT.error) === 0) return "error";
  if ((TEXT.step_blocked && raw.indexOf(TEXT.step_blocked) === 0) || raw.indexOf("401") !== -1) return "blocked";
  return "pending";
}
function setStatus(step, text) {
  const node = document.querySelector("[data-status-for='" + step + "']");
  if (node) { node.textContent = text; node.dataset.state = statusStateOf(text); }
  const card = document.querySelector("[data-step='" + step + "']");
  if (card) card.dataset.state = statusStateOf(text);
}
function startStatus(step) {
  const started = Date.now();
  setStatus(step, TEXT.running + " 0s");
  clearInterval(stepTimers[step]);
  stepTimers[step] = setInterval(() => {
    setStatus(step, TEXT.running + " " + Math.floor((Date.now() - started) / 1000) + "s");
  }, 500);
}
function stopStatus(step, text) { clearInterval(stepTimers[step]); setStatus(step, text); }
function decisionBlock(value) {
  const raw = String(value || "").toLowerCase();
  const label = raw === "block" ? "BLOCK" : (raw === "allow" ? "ALLOW" : "ASK");
  const node = el("div", label, "decision-block " + (raw || "ask_owner"));
  return node;
}
function statusBlocks(container, statuses) {
  clear(container);
  (statuses || []).forEach((s) => {
    container.appendChild(el("span", s, "code-block code-pop code-" + s));
  });
}
function miniBlocks(container, statuses) {
  if (!container) return;
  clear(container);
  (statuses || []).slice(-4).forEach((s) => {
    container.appendChild(el("span", s, "mini-code code-" + s));
  });
}
function anomalyText(a) {
  const kind = String((a && a.kind) || "");
  if (kind === "new_country") return TEXT.anomaly_new_country;
  if (kind === "new_model") return TEXT.anomaly_new_model;
  if (kind === "cost_spike") return TEXT.anomaly_cost_spike;
  if (kind === "blocked_burst") return TEXT.anomaly_blocked_burst;
  if (kind === "volume_spike") return TEXT.anomaly_volume_spike;
  if (kind === "out_of_range") return TEXT.anomaly_out_of_range;
  if (kind === "off_hours") return TEXT.anomaly_off_hours;
  if (kind === "unexpected_origin") return TEXT.anomaly_unexpected_origin;
  return TEXT.anomaly_other;
}
const REASON_EN = [
  ["inyección en documento no confiable deriva en acción con efecto", "Injection in an untrusted document leads to an action with effect"],
  ["documento no confiable pide revelar un secreto", "An untrusted document asks to reveal a secret"],
  ["lectura que llevaría a revelar un secreto, llave o token", "A read that would reveal a secret, key or token"],
  ["los argumentos piden revelar un secreto, llave o token", "The arguments ask to reveal a secret, key or token"],
  ["cambio de campo sensible derivado de fuente no confiable sospechosa", "Sensitive field change derived from a suspicious untrusted source"],
  ["cambio de campo sensible requiere aprobación del dueño", "Sensitive field change requires the owner's approval"],
  ["cambio de campo sensible no autorizado por la política", "Sensitive field change not authorized by policy"],
  ["fuente sospechosa sin clasificador: se escala al dueño", "Suspicious source without a classifier: escalated to the owner"],
  ["acción con efecto derivada de fuente no confiable: confirmar", "Action with effect derived from an untrusted source: confirm"],
  ["reglas deterministas: permitido", "Deterministic rules: allowed"]
];
function translateReason(value) {
  const raw = String(value || "");
  if (TEXT.lang_code !== "en") return raw;
  for (const [es, en] of REASON_EN) if (raw === es) return en;
  let m = raw.match(/^sin política para el agente (.+)$/); if (m) return "No policy for agent " + m[1];
  m = raw.match(/^herramienta no permitida para ([^:]+): (.+)$/); if (m) return "Tool not allowed for " + m[1] + ": " + m[2];
  m = raw.match(/^monto (.+) supera el límite (.+)$/); if (m) return "Amount " + m[1] + " exceeds the limit " + m[2];
  return raw;
}
function translateEvidence(value) {
  const raw = String(value || "");
  if (TEXT.lang_code !== "en") return raw;
  return raw.replace(/^field:/, "field:").replace(/^tool:/, "tool:").replace(/^effect:/, "effect:").replace(/^source:/, "source:").replace(/^amount:/, "amount:").replace(/^limit:/, "limit:").replace(/^agent:/, "agent:");
}
function hiddenNoteLine(text) {
  const lines = String(text || "").split(/\n|(?<=[.!?])\s+/);
  return lines.find((line) => /iban/i.test(line)) || lines.find((line) => /agente|agent/i.test(line)) || lines.find((line) => /cuenta|account/i.test(line)) || "";
}
function plainArgs(args) {
  return Object.entries(args || {}).map(([k, v]) => k + ": " + v).join(", ");
}
function renderInvoice(r) {
  const box = byId("invoiceResult"); clear(box);
  const tried = r.verdict_key ? r.verdict_key === "tried_update" : Object.values(r.runs || {}).some((run) => (run.attempted || []).some((a) => a.tool === "update_supplier_account"));
  box.appendChild(el("p", tried ? TEXT.verdict_tried : TEXT.verdict_no_bait, "verdict"));
  const review = r.spark_document_review;
  if (review) {
    const rowText = TEXT.lang_code === "es" ? (review.row_es || review.row_en || "") : (review.row_en || review.row_es || "");
    if (rowText) {
      const row = el("p", rowText);
      row.id = "sparkReviewRow";
      box.appendChild(row);
    }
  }
  const note = hiddenNoteLine(r.all_visible_text);
  if (note) box.appendChild(el("p", note, "hidden-note"));
  const details = document.createElement("details");
  details.appendChild(el("summary", TEXT.what_spark_read));
  details.appendChild(el("pre", r.all_visible_text || ""));
  box.appendChild(details);
  const cols = el("div", null, "columns");
  ["normal", "weak"].forEach((key) => {
    const run = (r.runs || {})[key] || {};
    const col = el("div");
    col.appendChild(el("h3", key === "weak" ? TEXT.weak_label : TEXT.normal_agent));
    if (run.content) col.appendChild(el("p", run.content));
    if (run.model_attempted_nothing || !(run.attempted || []).length) {
      col.appendChild(el("p", TEXT.no_attempt));
    }
    (run.attempted || []).forEach((att) => {
      col.appendChild(el("h4", TEXT.attempted + ": " + (att.tool || "")));
      col.appendChild(el("p", plainArgs(att.args)));
      col.appendChild(decisionBlock(att.decision));
      col.appendChild(el("p", TEXT.reason + ": " + translateReason(att.reason)));
      col.appendChild(el("p", TEXT.evidence + ": " + ((att.evidence || []).map(translateEvidence).join(", "))));
    });
    cols.appendChild(col);
  });
  box.appendChild(cols);
  const forced = r.forced_policy_test;
  if (forced) {
    const row = el("div", null, "forced-row");
    row.appendChild(el("h3", TEXT.forced_label));
    row.appendChild(el("p", (forced.tool || "") + ": " + plainArgs(forced.args)));
    row.appendChild(decisionBlock(forced.decision));
    row.appendChild(el("p", TEXT.reason + ": " + translateReason(forced.reason)));
    row.appendChild(el("p", TEXT.evidence + ": " + ((forced.evidence || []).map(translateEvidence).join(", "))));
    row.appendChild(el("p", TEXT.not_executed));
    box.appendChild(row);
  }
  box.appendChild(el("p", r.account_unchanged ? TEXT.supplier_unchanged : TEXT.supplier_changed, "verdict"));
  box.appendChild(el("p", TEXT.account_before_after + ": " + (r.account_before || "") + " / " + (r.account_after || "")));
}
function pctX(v, box) {
  const w = box.w || box.width;
  return w ? (v / w) * 100 : (Math.abs(v) <= 1 ? v * 100 : v / 10);
}
function pctY(v, box) {
  const h = box.h || box.height;
  return h ? (v / h) * 100 : (Math.abs(v) <= 1 ? v * 100 : v / 10);
}
function renderCount(r) {
  byId("countValue").textContent = String(r.count ?? "") + " " + TEXT.boxes_counted;
  byId("materialLabel").textContent = r.material_label || "";
  byId("expectedLine").textContent = r.is_fixture ? TEXT.expected_7 : "";
  const overlay = byId("shelfOverlay"); clear(overlay);
  (r.boxes || []).forEach((item) => {
    const box = item.box || item || {};
    const x1 = box.x_min ?? box.x1 ?? box.x ?? 0;
    const y1 = box.y_min ?? box.y1 ?? box.y ?? 0;
    const x2 = box.x_max ?? box.x2 ?? ((box.x1 ?? box.x ?? 0) + (box.w || 0));
    const y2 = box.y_max ?? box.y2 ?? ((box.y1 ?? box.y ?? 0) + (box.h || 0));
    const node = el("div", null, "box-overlay");
    node.style.left = pctX(x1, box) + "%";
    node.style.top = pctY(y1, box) + "%";
    node.style.width = Math.max(0, pctX(x2, box) - pctX(x1, box)) + "%";
    node.style.height = Math.max(0, pctY(y2, box) - pctY(y1, box)) + "%";
    overlay.appendChild(node);
  });
}
function renderAttack(r) {
  statusBlocks(byId("attackStatuses"), r.statuses || []);
  const list = byId("anomalyList"); clear(list);
  (r.anomalies || []).forEach((a) => list.appendChild(el("li", anomalyText(a))));
}
function actionPlain(action) {
  const map = {rotate_token: TEXT.action_rotate_token, verify: TEXT.action_verify, draft_notice: TEXT.action_draft_notice, rotate_upstream_key: TEXT.action_rotate_upstream_key};
  return map[action] || String(action || "");
}
function renderGuardian(r) {
  const box = byId("guardianResult"); clear(box);
  const turns = r.turns || [];
  const toolCount = turns.reduce((n, t) => n + ((t.tool_calls || []).length), 0);
  if (turns.length) box.appendChild(el("p", TEXT.guardian_turns + ": " + turns.length + " " + TEXT.turns_used + " · " + toolCount + " " + TEXT.tools_used));
  if (r.status === "error" || !r.plan) {
    box.appendChild(el("p", r.error || TEXT.no_plan_error));
    return;
  }
  const plan = r.plan;
  box.appendChild(el("h3", TEXT.plan_summary));
  box.appendChild(el("p", plan.summary || ""));
  box.appendChild(el("h3", TEXT.plan_reasoning));
  box.appendChild(el("p", plan.reasoning || ""));
  box.appendChild(el("h3", TEXT.plan_exposures));
  const exList = el("ul");
  (plan.exposures || []).forEach((ex) => exList.appendChild(el("li", (ex.advisory_id || "") + " → " + (ex.asset_id || "") + (ex.reason ? ": " + ex.reason : ""))));
  box.appendChild(exList);
  box.appendChild(el("h3", TEXT.plan_steps));
  const stepList = el("ol");
  (plan.steps || []).forEach((s) => stepList.appendChild(el("li", actionPlain(s.action) + " — " + (s.target || "") + (s.reason ? " — " + s.reason : ""))));
  box.appendChild(stepList);
  if (turns.length) box.appendChild(el("h3", TEXT.guardian_turns));
  turns.forEach((turn) => {
    const details = document.createElement("details");
    details.appendChild(el("summary", "Turn " + (turn.turn || "")));
    if (turn.content) details.appendChild(el("p", turn.content));
    (turn.tool_calls || []).forEach((call) => details.appendChild(el("p", (call.name || "") + ": " + plainArgs(call.args))));
    (turn.tool_results || []).forEach((res) => details.appendChild(el("pre", (res.name || "") + ": " + (res.result || ""))));
    box.appendChild(details);
  });
}
function intentPlain(intent) {
  const action = intent.action === "approve" ? TEXT.intent_approve : (intent.action === "reject" ? TEXT.intent_reject : TEXT.intent_unknown);
  const parts = [action];
  if ((intent.exclude_targets || []).length) parts.push(TEXT.intent_except + " " + intent.exclude_targets.join(", "));
  if ((intent.only_targets || []).length) parts.push(TEXT.intent_only + " " + intent.only_targets.join(", "));
  return parts.join(" — ");
}
function renderVoice(r) {
  byId("voiceTranscript").textContent = r.transcript || "";
  const channelNode = byId("voiceChannel");
  if (channelNode) {
    if (r.channel === "whatsapp") channelNode.textContent = r.status === "approved" ? TEXT.voice_via_whatsapp : TEXT.voice_via_whatsapp_note;
    else if (r.channel === "browser") channelNode.textContent = TEXT.voice_via_browser;
    else channelNode.textContent = "";
  }
  const bubble = byId("whatsappBubble");
  if (bubble) {
    bubble.classList.toggle("is-whatsapp", r.channel === "whatsapp");
    bubble.classList.toggle("is-approved", r.channel === "whatsapp" && r.status === "approved");
    bubble.dataset.channel = r.channel || "";
  }
  const approvedLine = byId("whatsappApprovedLine");
  if (approvedLine) approvedLine.textContent = (r.channel === "whatsapp" && r.status === "approved") ? TEXT.approved_via_whatsapp : "";
  const intent = r.intent || {};
  byId("voiceIntent").textContent = intentPlain(intent);
  const showConfirm = r.status === "confirmation_required";
  byId("voiceConfirm").hidden = !showConfirm;
  byId("voiceCancel").hidden = !showConfirm;
  byId("disagreeLine").textContent = intent.source === "disagreement" ? TEXT.disagreement : "";
  byId("voiceStatusLine").textContent = r.status === "unknown_command" ? TEXT.voice_unknown : (r.status === "no_speech" ? TEXT.voice_no_speech : (r.status === "error" ? TEXT.error + ": " + (r.error || "") : (r.status || "")));
}
function sdkSequenceText(statuses) {
  const parts = [];
  (statuses || []).forEach((s, idx) => {
    if (idx > 0 && statuses[idx - 1] === 401 && s === 200) parts.push(TEXT.sdk_refreshed);
    parts.push(String(s));
  });
  return "Warehouse SDK: " + parts.join(" → ");
}
function renderContain(r, state) {
  const before = ((state && state.results && state.results.attack) || {}).statuses || [];
  statusBlocks(byId("attackerBefore"), before);
  statusBlocks(byId("attackerAfter"), r.attacker_after || []);
  byId("sdkLine").textContent = sdkSequenceText(r.sdk_statuses || []);
  byId("recountLine").textContent = TEXT.recount_after + ": " + ((r.recount || {}).count ?? "");
  byId("comprasLine").textContent = TEXT.purchasing_status + ": " + (r.compras_status ?? "");
  byId("containedLine").textContent = r.contained_in_s != null ? TEXT.contained_in + " " + r.contained_in_s + "s" : "";
}
function coldAttempt(att, label) {
  const row = el("div", null, "forced-row");
  const eq = (att.equipment || {});
  const req = (att.request || {});
  row.appendChild(el("h3", label || (eq.label || req.equipment || "")));
  row.appendChild(el("p", (eq.label || req.equipment || "") + ": " + (req.setpoint_c !== undefined ? req.setpoint_c + " °C" : "") + (req.hour !== undefined ? " · " + String(req.hour).padStart(2, "0") + ":00" : "") + (req.origin_country ? " · " + req.origin_country : "")));
  row.appendChild(decisionBlock(att.decision));
  (att.reasons || []).forEach((reason) => row.appendChild(el("p", reason, "mono")));
  row.appendChild(el("p", att.applied ? TEXT.cold_applied : TEXT.cold_not_applied));
  return row;
}
function renderColdLegit(r) {
  const box = byId("invoiceResult"); clear(box);
  box.appendChild(el("p", TEXT.cold_legit_note, "verdict"));
  box.appendChild(coldAttempt(r.evaluation || {}));
  box.appendChild(el("p", "Gateway: " + (r.gateway_status ?? "")));
}
function renderColdScope(r) {
  const box = byId("countResult"); clear(box);
  box.appendChild(el("p", TEXT.cold_scope_note, "verdict"));
  box.appendChild(coldAttempt(r.evaluation || {}));
}
function renderColdAttack(r) {
  renderAttack(r);
  const box = byId("coldAttempts"); clear(box);
  (r.attacks || []).forEach((att) => box.appendChild(coldAttempt(att)));
}
function renderColdContain(r, state) {
  const before = ((state && state.results && state.results.attack) || {}).statuses || [];
  statusBlocks(byId("attackerBefore"), before.slice(0, 1));
  statusBlocks(byId("attackerAfter"), r.attacker_after || []);
  byId("sdkLine").textContent = TEXT.cold_refrigeration_status + ": " + (r.refrigeracion_status ?? "");
  byId("recountLine").textContent = TEXT.warehouse_status + ": " + (r.bodega_status ?? "");
  byId("comprasLine").textContent = TEXT.purchasing_status + ": " + (r.compras_status ?? "");
  byId("containedLine").textContent = r.contained_in_s != null ? TEXT.contained_in + " " + r.contained_in_s + "s" : "";
}
function renderResult(step, r, state) {
  if (!r) return;
  if (SCENE === "frio") {
    if (step === "invoice") return renderColdLegit(r);
    if (step === "count") return renderColdScope(r);
    if (step === "attack") return renderColdAttack(r);
    if (step === "contain") return renderColdContain(r, state);
  }
  if (step === "invoice") renderInvoice(r);
  if (step === "count") renderCount(r);
  if (step === "attack") renderAttack(r);
  if (step === "guardian") renderGuardian(r);
  if (step === "voice") {
    const base = ((state && state.results && state.results.voice) || (state && state.voice) || {});
    renderVoice({...base, ...r, transcript: r.transcript || base.transcript || "", intent: r.intent || base.intent || {}, channel: r.channel || base.channel || ""});
  }
  if (step === "contain") renderContain(r, state);
}
/* Esfera de partículas: reacciona al estado que llega de /live/state. */
let sphereMode = "calm";
let sphereWaveAt = 0;
function setSphereMode(mode) {
  if (mode === sphereMode) return;
  sphereMode = mode;
  if (mode === "approved") sphereWaveAt = performance.now();
  if (sphereReduced) drawSphere(0);
}
let sphereReduced = false;
let drawSphere = function () {};
(function initSphere() {
  const canvas = document.getElementById("sphereCanvas");
  if (!canvas || !canvas.getContext) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  sphereReduced = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const COUNT = 640;
  const parts = [];
  for (let i = 0; i < COUNT; i++) {
    let u = Math.random() * 2 - 1;
    if (i % 3 === 0) u *= 0.35;
    const theta = Math.random() * Math.PI * 2;
    const ring = Math.sqrt(Math.max(0, 1 - u * u));
    parts.push({
      x: ring * Math.cos(theta),
      y: u,
      z: ring * Math.sin(theta),
      size: 0.7 + Math.random() * 1.8,
      len: 5 + Math.random() * 13,
      stroke: Math.random() < 0.46,
      phase: Math.random() * Math.PI * 2,
      alt: Math.random() < 0.5,
      rgb: [232, 236, 244]
    });
  }
  let W = 0, H = 0, raf = 0, visible = true;
  function resize() {
    const host = canvas.parentElement;
    if (!host) return;
    const rect = host.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    W = Math.max(1, rect.width); H = Math.max(1, rect.height);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (sphereReduced) drawSphere(0);
  }
  function targetFor(p, waveDist) {
    if (sphereMode === "attack") return p.alt ? [248, 113, 113] : [251, 191, 36];
    if (sphereMode === "approved") return waveDist < 0.09 ? [147, 197, 253] : [96, 165, 250];
    if (sphereMode === "contained") return p.alt ? [110, 231, 183] : [125, 211, 252];
    return [232, 236, 244];
  }
  const copyEl = canvas.parentElement ? canvas.parentElement.querySelector(".hero-copy") : null;
  function haloRgb() {
    if (sphereMode === "attack") return "248,113,113";
    if (sphereMode === "approved") return "96,165,250";
    if (sphereMode === "contained") return "110,231,183";
    return "210,220,235";
  }
  drawSphere = function (now) {
    if (!W || !H) return;
    ctx.clearRect(0, 0, W, H);
    let cx = W / 2, cy = H / 2;
    if (copyEl) {
      const cr = canvas.getBoundingClientRect();
      const hr = copyEl.getBoundingClientRect();
      if (hr.width) { cx = hr.left - cr.left + hr.width / 2; cy = hr.top - cr.top + hr.height / 2; }
    }
    const vh = window.innerHeight || H;
    const R = Math.max(60, Math.min(vh * 0.35, W * 0.47, H * 0.46));
    const t = sphereReduced ? 0 : now;
    const halo = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.25);
    halo.addColorStop(0, "rgba(" + haloRgb() + ",0.13)");
    halo.addColorStop(0.65, "rgba(" + haloRgb() + ",0.05)");
    halo.addColorStop(1, "rgba(" + haloRgb() + ",0)");
    ctx.fillStyle = halo;
    ctx.beginPath(); ctx.arc(cx, cy, R * 1.25, 0, Math.PI * 2); ctx.fill();
    const rotY = t * 0.00011 * (sphereMode === "attack" ? 2.3 : 1);
    const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
    const tilt = 0.42, cosX = Math.cos(tilt), sinX = Math.sin(tilt);
    const amp = sphereMode === "attack" ? 3.4 : (sphereMode === "approved" ? 1.2 : 0.5);
    const focal = 3.1;
    let wave = -1;
    if (sphereMode === "approved" && !sphereReduced) wave = ((now - sphereWaveAt) % 2400) / 2400;
    const sorted = parts.map((p) => {
      const x1 = p.x * cosY + p.z * sinY;
      const z1 = -p.x * sinY + p.z * cosY;
      const y2 = p.y * cosX - z1 * sinX;
      const z2 = p.y * sinX + z1 * cosX;
      return {p: p, x: x1, y: y2, z: z2};
    }).sort((a, b) => a.z - b.z);
    for (const item of sorted) {
      const p = item.p;
      const scale = focal / (focal - item.z);
      let sx = cx + item.x * R * scale;
      let sy = cy + item.y * R * scale;
      const radial = Math.min(1, Math.sqrt(item.x * item.x + item.y * item.y));
      const waveDist = wave >= 0 ? Math.abs(radial - wave) : 1;
      const target = targetFor(p, waveDist);
      for (let c = 0; c < 3; c++) p.rgb[c] += (target[c] - p.rgb[c]) * 0.07;
      if (!sphereReduced) {
        const jig = Math.sin(t * (sphereMode === "attack" ? 0.012 : 0.0016) + p.phase) * amp;
        const d = Math.sqrt((sx - cx) * (sx - cx) + (sy - cy) * (sy - cy)) || 1;
        sx += ((sx - cx) / d) * jig; sy += ((sy - cy) / d) * jig;
        if (waveDist < 0.09) { sx += ((sx - cx) / d) * (0.09 - waveDist) * 70; sy += ((sy - cy) / d) * (0.09 - waveDist) * 70; }
      }
      const depth = (item.z + 1) / 2;
      const alpha = (0.14 + radial * 0.5 + depth * 0.3) * (sphereMode === "calm" ? 0.95 : 1);
      ctx.strokeStyle = "rgba(" + Math.round(p.rgb[0]) + "," + Math.round(p.rgb[1]) + "," + Math.round(p.rgb[2]) + "," + Math.min(0.95, alpha).toFixed(3) + ")";
      ctx.fillStyle = ctx.strokeStyle;
      if (p.stroke) {
        const dx = sx - cx, dy = sy - cy, dl = Math.sqrt(dx * dx + dy * dy) || 1;
        const seg = p.len * scale * (0.55 + radial * 0.7);
        ctx.beginPath();
        ctx.moveTo(sx, sy);
        ctx.lineTo(sx + (dx / dl) * seg, sy + (dy / dl) * seg);
        ctx.lineWidth = Math.max(0.7, scale * 0.9);
        ctx.stroke();
      } else {
        ctx.beginPath();
        ctx.arc(sx, sy, Math.max(0.5, p.size * scale), 0, Math.PI * 2);
        ctx.fill();
      }
    }
  };
  function frame(now) {
    drawSphere(now);
    raf = requestAnimationFrame(frame);
  }
  function start() {
    if (sphereReduced || raf || document.hidden || !visible) return;
    raf = requestAnimationFrame(frame);
  }
  function stop() { if (raf) cancelAnimationFrame(raf); raf = 0; }
  document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); else start(); });
  if ("IntersectionObserver" in window) {
    new IntersectionObserver((entries) => {
      visible = !entries.length || entries[0].isIntersecting;
      if (visible) start(); else stop();
    }).observe(canvas);
  }
  window.addEventListener("resize", resize);
  resize();
  if (sphereReduced) drawSphere(0); else start();
})();
let lastState = null;
let clockTimer = null;
function updateBand(state) {
  lastState = state || lastState;
  if (!state) return;
  const total = Number(state.total_cost_usd || 0);
  const cap = Number(state.cap_usd || 1);
  byId("costLabel").textContent = REPLAY ? TEXT.replay_cost : "USD " + total.toFixed(4) + " " + TEXT.cost_of_cap.replace("{cap}", cap.toFixed(2));
  const stickyCost = byId("stickyCost");
  if (stickyCost) stickyCost.textContent = byId("costLabel").textContent;
  const results = state.results || {};
  const contained = results.contain && (results.contain.attacker_after || []).includes(401);
  const voice = results.voice || state.voice || {};
  if (contained) setSphereMode("contained");
  else if (voice.status === "approved") setSphereMode("approved");
  else if (results.attack) setSphereMode("attack");
  else setSphereMode("calm");
  let headline = TEXT.headline_start;
  if (contained) headline = TEXT.headline_contained;
  else if (results.guardian) headline = TEXT.headline_waiting;
  else if (results.attack) headline = TEXT.headline_attack;
  byId("headline").textContent = headline;
  const strip = [];
  if (results.attack) strip.push(...(results.attack.statuses || []));
  if (results.contain) strip.push(...(results.contain.attacker_after || []));
  statusBlocks(byId("attackerStrip"), strip);
  miniBlocks(byId("stickyAttacker"), strip);
  miniBlocks(byId("stickySdk"), results.contain ? (results.contain.sdk_statuses || []) : []);
  if (state.status === "no_key") {
    byId("noKeyBox").hidden = false;
    byId("noKeyBox").textContent = TEXT.no_key + ": " + (state.no_key_message || TEXT.no_key_body);
  }
  const provBody = byId("provBody"); clear(provBody);
  const fmtCost = (v) => {
    const n = Number(v || 0);
    let s = n.toFixed(6);
    while (s.includes(".") && s.endsWith("0") && s.split(".")[1].length > 4) s = s.slice(0, -1);
    return s;
  };
  (state.provenance || []).forEach((p) => {
    const tr = document.createElement("tr");
    const values = [p.step, p.agent, p.model || "—", p.response_id || "—", Math.round(Number(p.latency_ms || 0)), p.input_tokens, p.output_tokens, fmtCost(p.cost_usd), p.http_status, p.decision || "—"];
    values.forEach((v, idx) => {
      const td = el("td", v === null || v === undefined ? "" : v, idx === 3 ? "mono" : "");
      tr.appendChild(td);
    });
    provBody.appendChild(tr);
  });
  clearInterval(clockTimer);
  const snapshot = {receivedAt: Date.now(), duration_s: Number(state.duration_s || 0), contained_in_s: state.contained_in_s};
  const tickClock = () => {
    const contained = snapshot.contained_in_s != null;
    byId("bigClock").dataset.state = contained ? "contained" : (results.attack ? "attack" : "calm");
    const elapsed = (Date.now() - snapshot.receivedAt) / 1000;
    byId("chainDuration").textContent = fmtClock(contained ? snapshot.duration_s : snapshot.duration_s + elapsed);
    const label = byId("clockLabel");
    if (contained) {
      if (label) label.textContent = TEXT.time_to_401;
      byId("bigClock").textContent = fmtClock(snapshot.contained_in_s);
    } else if (results.attack && results.attack.attack_started_at) {
      if (label) label.textContent = TEXT.time_since_attack;
      byId("bigClock").textContent = fmtClock((Date.now() - Date.parse(results.attack.attack_started_at)) / 1000);
    } else {
      if (label) label.textContent = TEXT.time_to_401;
      byId("bigClock").textContent = "--:--";
    }
    const stickyClock = byId("stickyClock");
    if (stickyClock) { stickyClock.textContent = byId("bigClock").textContent; stickyClock.dataset.state = byId("bigClock").dataset.state || "calm"; }
    const stickyLabel = byId("stickyClockLabel");
    if (stickyLabel && label) stickyLabel.textContent = label.textContent;
  };
  tickClock();
  clockTimer = setInterval(tickClock, 1000);
  Object.keys(results).forEach((key) => renderResult(key === "voice_confirm" || key === "voice_cancel" ? "voice" : key, results[key], state));
}
async function refreshState() {
  const res = await fetch(API + "/state");
  if (!res.ok) return null;
  const state = await res.json();
  if (state.status === "not_started") {
    const started = await fetch(API + "/start", {method: "POST"});
    if (started.ok) { const s2 = await started.json(); updateBand(s2); return s2; }
    return state;
  }
  updateBand(state);
  return state;
}
async function runStep(step) {
  startStatus(step);
  try {
    let res;
    if (step === "count") {
      const input = byId("ownPhoto");
      if (input && input.files && input.files[0]) {
        byId("shelfImg").src = URL.createObjectURL(input.files[0]);
        const form = new FormData();
        form.append("file", input.files[0]);
        res = await fetch(API + "/step/count", {method: "POST", body: form});
      } else {
        res = await fetch(API + "/step/count", {method: "POST"});
      }
    } else {
      res = await fetch(API + "/step/" + step, {method: "POST"});
    }
    const data = await res.json();
    if (!res.ok || data.status === "error" || data.status === "cost_cap_reached" || data.status === "not_approved") {
      stopStatus(step, TEXT.error + ": " + (data.error || data.status || res.status));
    } else {
      stopStatus(step, TEXT.ok);
    }
    renderResult(step, data, lastState);
    await refreshState();
    return data;
  } catch (err) {
    stopStatus(step, TEXT.error + ": " + err.message);
    return {status: "error", error: err.message};
  }
}
async function runUntilOwner() {
  for (const step of ["invoice", "count", "attack", "guardian"]) {
    const data = await runStep(step);
    if (!data || data.status === "error" || data.status === "cost_cap_reached") break;
  }
}
// mono PCM16 16 kHz WAV
function buildWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeText = (offset, text) => { for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i)); };
  writeText(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); writeText(8, "WAVE");
  writeText(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  writeText(36, "data"); view.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) => {
    const clamped = Math.max(-1, Math.min(1, s));
    view.setInt16(44 + i * 2, clamped < 0 ? clamped * 32768 : clamped * 32767, true);
  });
  return new Blob([view], {type: "audio/wav"});
}
function resampleTo16k(chunks, inRate) {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const merged = new Float32Array(total);
  let offset = 0;
  chunks.forEach((c) => { merged.set(c, offset); offset += c.length; });
  const ratio = inRate / 16000;
  const outLength = Math.floor(merged.length / ratio);
  const out = new Float32Array(outLength);
  for (let i = 0; i < outLength; i++) out[i] = merged[Math.floor(i * ratio)] || 0;
  return out;
}
let recording = null;
async function toggleRecord() {
  const btn = byId("recordBtn");
  if (recording) {
    const current = recording; recording = null;
    btn.textContent = TEXT.record;
    clearInterval(current.timer);
    current.processor.disconnect(); current.source.disconnect();
    current.stream.getTracks().forEach((t) => t.stop());
    await current.ctx.close();
    const samples = resampleTo16k(current.chunks, current.rate);
    let sumSq = 0;
    samples.forEach((s) => { sumSq += s * s; });
    const rms = samples.length ? Math.sqrt(sumSq / samples.length) : 0;
    byId("voiceLevel").textContent = TEXT.level_label + ": " + rms.toFixed(4);
    if (rms < 0.001) {
      byId("micError").textContent = TEXT.mic_silence;
      byId("voiceStatusLine").textContent = TEXT.voice_no_speech;
      stopStatus("voice", TEXT.voice_no_speech);
      return;
    }
    const wav = buildWav(samples, 16000);
    const form = new FormData();
    form.append("file", wav, "voz.wav");
    startStatus("voice");
    const res = await fetch(API + "/voice", {method: "POST", body: form});
    const data = await res.json();
    stopStatus("voice", data.status === "error" ? TEXT.error + ": " + (data.error || "") : TEXT.ok + ": " + (data.status || ""));
    renderVoice(data);
    await refreshState();
    if (data.status === "approved") await runStep("contain");
    return;
  }
  try {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error("no microphone");
    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
    const ctx = new AudioContext();
    await ctx.resume();
    const source = ctx.createMediaStreamSource(stream);
    const processor = ctx.createScriptProcessor(4096, 1, 1);
    const chunks = [];
    processor.onaudioprocess = (event) => {
      const data = new Float32Array(event.inputBuffer.getChannelData(0));
      chunks.push(data);
      let sumSq = 0;
      data.forEach((s) => { sumSq += s * s; });
      byId("voiceLevel").textContent = TEXT.level_label + ": " + Math.sqrt(sumSq / Math.max(1, data.length)).toFixed(4);
    };
    source.connect(processor); processor.connect(ctx.destination);
    const started = Date.now();
    const timer = setInterval(() => { byId("recordTimer").textContent = TEXT.recording + " " + Math.floor((Date.now() - started) / 1000) + "s"; }, 250);
    recording = {stream, ctx, source, processor, chunks, rate: ctx.sampleRate, timer};
    btn.textContent = TEXT.stop;
  } catch (err) {
    byId("micError").textContent = TEXT.no_mic;
    byId("typedText").focus();
  }
}
/* «New run» limpia ya la transcripción y los resultados de la corrida anterior
   (antes quedaban a la vista hasta que la página terminaba de recargar). */
function clearRun() {
  Object.keys(stepTimers).forEach((k) => clearInterval(stepTimers[k]));
  ["voiceTranscript", "voiceIntent", "voiceStatusLine", "voiceChannel", "disagreeLine",
   "voiceLevel", "micError", "recordTimer", "containedLine", "sdkLine", "recountLine",
   "comprasLine", "countValue", "expectedLine", "approvedLine"].forEach((id) => {
    const node = byId(id); if (node) node.textContent = "";
  });
  ["attackerBefore", "attackerAfter"].forEach((id) => { const n = byId(id); if (n) n.replaceChildren(); });
  const typed = byId("typedText"); if (typed) typed.value = "";
  ["voiceConfirm", "voiceCancel"].forEach((id) => { const n = byId(id); if (n) n.hidden = true; });
  document.querySelectorAll("[data-status-for]").forEach((n) => {
    n.textContent = TEXT.not_run; n.dataset.state = "pending";
  });
  document.querySelectorAll(".step").forEach((n) => { n.dataset.state = "pending"; });
  const bubble = byId("whatsappBubble");
  if (bubble) { bubble.classList.remove("is-whatsapp", "is-approved"); bubble.dataset.channel = ""; }
}
document.addEventListener("DOMContentLoaded", () => {
  byId("runUntilBtn").addEventListener("click", runUntilOwner);
  byId("newRunBtn").addEventListener("click", async () => {
    await fetch(API + "/reset", {method: "POST"});
    clearRun();
    window.location.reload();
  });
  const stickyBtn = byId("stickyNewRunBtn");
  if (stickyBtn) stickyBtn.addEventListener("click", () => byId("newRunBtn").click());
  document.querySelectorAll("[data-run-step]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const step = btn.getAttribute("data-run-step");
      if (step === "voice") { if (REPLAY) { byId("typedText").focus(); } else { toggleRecord(); } return; }
      runStep(step);
    });
  });
  byId("recordBtn").addEventListener("click", toggleRecord);
  if (REPLAY) {
    const typed = byId("typedText");
    if (typed && !typed.value) typed.value = TEXT.replay_phrase;
  }
  byId("sendTypedBtn").addEventListener("click", async () => {
    const form = new FormData();
    form.append("typed", byId("typedText").value);
    startStatus("voice");
    const res = await fetch(API + "/voice", {method: "POST", body: form});
    const data = await res.json();
    stopStatus("voice", data.status === "error" ? TEXT.error + ": " + (data.error || "") : TEXT.ok + ": " + (data.status || ""));
    renderVoice(data);
    await refreshState();
    if (data.status === "approved") await runStep("contain");
  });
  byId("voiceConfirm").addEventListener("click", async () => {
    const res = await fetch(API + "/voice/confirm", {method: "POST"});
    const data = await res.json();
    byId("voiceStatusLine").textContent = data.status || "";
    await refreshState();
    if (data.status === "approved") await runStep("contain");
  });
  byId("voiceCancel").addEventListener("click", async () => {
    const res = await fetch(API + "/voice/cancel", {method: "POST"});
    const data = await res.json();
    byId("voiceStatusLine").textContent = data.status || "";
    await refreshState();
  });
  refreshState();
});
"""




def _step_html(number: int, step: str, title: str, lang: str, inner: str) -> str:
    return (
        f"<li class='step' data-step='{step}' data-state='pending'>"
        f"<div class='step-head'><span class='step-num'>{number}</span><h2>{_e(title)}</h2>"
        f"<span class='step-status' data-status-for='{step}' data-state='pending' aria-live='polite'>"
        f"{_e(_t(lang, 'not_run'))}</span>"
        f"<button class='btn secondary' type='button' data-run-step='{step}'>"
        f"{_e(_t(lang, 'run_step'))}</button></div>"
        f"<div class='result'>{inner}</div></li>"
    )


def render_live_page(
    lang: str = "en",
    *,
    spark_open_no_key: bool = True,
    no_key: bool = False,
    remote: bool = False,
    replay_url: str = "/",
    replay: bool = False,
    scene: str = "bodega",
) -> str:
    import json as _json

    lang = lang if lang in T else "en"
    scene = scene if scene in ("bodega", "frio") else "bodega"
    cold = replay and scene == "frio"
    api = "/replay" if replay else "/live"
    labels = dict(T[lang])
    if cold:
        labels["hero_subtitle"] = labels["cold_hero_subtitle"]
        labels["voice_hint"] = labels["cold_voice_hint"]
        labels["replay_phrase"] = labels["cold_replay_phrase"]
        labels["step1_title"] = labels["cold_step1_title"]
        labels["step2_title"] = labels["cold_step2_title"]
        labels["step3_title"] = labels["cold_step3_title"]
    if replay:
        labels["live_label"] = labels["replay_label"]
        if not cold:
            labels["hero_subtitle"] = labels["replay_hero_subtitle"]
    if remote:
        labels["live_label"] = (
            "LIVE — real Meta models through the Shield gateway (hosted, spend capped)"
            if lang == "en"
            else "EN VIVO — modelos reales de Meta a través del gateway de Shield (alojado, gasto con tope)"
        )
    def _L(key: str) -> str:
        return labels.get(key) or T["en"].get(key, key)

    texts = _json.dumps(labels, ensure_ascii=False)
    script = (
        _JS.replace("__TEXTS__", texts)
        .replace("__API__", api)
        .replace("__SCENE__", scene)
        .replace("__REPLAY__", "true" if replay else "false")
    )
    en_current = " aria-current='true'" if lang == "en" else ""
    es_current = " aria-current='true'" if lang == "es" else ""
    spark_row = _L("spark_open_row") if spark_open_no_key else _L("spark_open_row_key")
    if cold:
        step1_inner = "<div id='invoiceResult'></div>"
        step2_inner = "<div id='countResult'></div>"
    else:
        step1_inner = (
            "<div class='invoice-media'>"
            f"<img class='thumb' src='{api}/fixture/invoice' alt='invoice fixture'>"
            f"<div class='fineprint-wrap'><img class='fineprint' src='{api}/fixture/invoice' "
            "alt='invoice fine print'></div></div>"
            f"<p>{_e(_L('hidden_order'))}</p><div id='invoiceResult'></div>"
        )
        step2_inner = (
            f"<div class='shelf-wrap'><img id='shelfImg' src='{api}/fixture/shelf' alt='shelf fixture'>"
            "<div id='shelfOverlay'></div></div>"
            "<p class='bigcount' id='countValue'></p>"
            "<p id='materialLabel'></p><p id='expectedLine'></p>"
            "<label class='file-pill' for='ownPhoto'><input class='file-input' id='ownPhoto' type='file' accept='image/*'>"
            f"<span>{_e(_L('use_own_photo'))}</span></label>"
        )
    step3_inner = (
        f"<p>{_e(_L('attacker_attempts'))}</p>"
        "<div id='attackStatuses' class='attempts'></div>"
        + ("<div id='coldAttempts'></div>" if cold else "")
        + f"<h3>{_e(_L('anomalies'))}</h3><ul id='anomalyList'></ul>"
    )
    step4_inner = f"<p>{_e(_L('demo_inventory'))}</p><div id='guardianResult'></div>"
    step5_inner = (
        ""
        + (
            f"<p class='replay-note'>{_e(_L('replay_voice_note'))}</p>"
            "<button class='btn primary' id='recordBtn' type='button' hidden></button>"
            " <span id='recordTimer' aria-live='polite' hidden></span>"
            "<p id='micError' aria-live='polite' hidden></p><p id='voiceLevel' aria-live='polite' hidden></p>"
            if replay
            else f"<button class='btn primary' id='recordBtn' type='button'>{_e(_L('record'))}</button>"
            " <span id='recordTimer' aria-live='polite'></span>"
            "<p id='micError' aria-live='polite'></p><p id='voiceLevel' aria-live='polite'></p>"
        )
        + f"<label for='typedText'>{_e(_L('typed_fallback'))}</label>"
        "<input id='typedText' type='text'>"
        f"<p>{html.escape(_L('voice_hint'), quote=False)}</p>"
        f"<button class='btn secondary' id='sendTypedBtn' type='button'>{_e(_L('send_typed'))}</button>"
        "<div id='whatsappBubble' class='chat-bubble'>"
        f"<p class='chat-head'><span class='chat-badge'>{_e(_L('whatsapp_note_title'))}</span></p>"
        f"<h3>{_e(_L('transcript'))}</h3><p id='voiceChannel' aria-live='polite'></p>"
        "<p id='voiceTranscript' class='chat-text'></p>"
        f"<h3>{_e(_L('spark_intent'))}</h3><p id='voiceIntent' class='mono'></p>"
        "<p id='whatsappApprovedLine' class='chat-approved' aria-live='polite'></p></div>"
        "<p id='disagreeLine'></p><p id='voiceStatusLine' aria-live='polite'></p>"
        f"<button class='btn primary' id='voiceConfirm' type='button' hidden>{_e(_L('confirm'))}</button>"
        f" <button class='btn secondary' id='voiceCancel' type='button' hidden>{_e(_L('cancel'))}</button>"
    )
    step6_inner = (
        f"<p>{_e(_L('attacker_before'))}</p><div id='attackerBefore' class='attempts'></div>"
        f"<p>{_e(_L('attacker_after'))}</p><div id='attackerAfter' class='attempts'></div>"
        "<p id='sdkLine'></p><p id='recountLine'></p><p id='comprasLine'></p>"
        "<p id='containedLine'></p>"
    )
    steps = "".join(
        [
            _step_html(1, "invoice", _L("step1_title"), lang, step1_inner),
            _step_html(2, "count", _L("step2_title"), lang, step2_inner),
            _step_html(3, "attack", _L("step3_title"), lang, step3_inner),
            _step_html(4, "guardian", _L("step4_title"), lang, step4_inner),
            _step_html(5, "voice", _L("step5_title"), lang, step5_inner),
            _step_html(6, "contain", _L("step6_title"), lang, step6_inner),
        ]
    )
    no_key_hidden = "" if no_key and not replay else " hidden"
    if replay:
        mode_switch = (
            f"<nav class='mode-switch'><a href='/?scene={scene}&lang={lang}' aria-current='true'>{_e(_L('replay'))}</a>"
            f"<span class='mode-off' aria-disabled='true' title='{_e(_L('live_off_note'))}'>{_e(_L('live_off'))}</span></nav>"
        )
        scene_switch = (
            f"<nav class='mode-switch scene-switch' aria-label='{_e(_L('scene_label'))}'>"
            f"<a href='/?scene=bodega&lang={lang}'{' aria-current=\'true\'' if scene == 'bodega' else ''}>{_e(_L('scene_bodega'))}</a>"
            f"<a href='/?scene=frio&lang={lang}'{' aria-current=\'true\'' if scene == 'frio' else ''}>{_e(_L('scene_frio'))}</a></nav>"
        )
        lang_base = f"/?scene={scene}&"
        live_off_block = f"<p class='live-off-note'>{_e(_L('live_off_note'))}</p>"
        prov_note = _L("replay_cold_provenance_note" if cold else "replay_provenance_note")
    else:
        mode_switch = (
            f"<nav class='mode-switch'><a href='{_e(replay_url)}'>{_e(_L('replay'))}</a>"
            f"<a href='/live' aria-current='true'>{_e(_L('live'))}</a></nav>"
        )
        scene_switch = ""
        lang_base = "/live?"
        live_off_block = ""
        prov_note = ""
    return (
        "<!doctype html>\n"
        f"<html lang='{_e(lang)}'><head><meta charset='utf-8'>"
        "<link rel='icon' href='data:,'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_e(BRAND)} — {_e(SUBTITLE)} live</title>"
        f"<style>{_CSS}</style></head><body>"
        "<header class='band'><div class='inner'>"
        "<div class='band-top'>"
        f"<p class='brandline'><strong>{_e(BRAND)}</strong> · {_e(SUBTITLE)}</p>"
        f"<span class='live-label'>{_e(labels['live_label'])}</span>"
        "<div class='band-tools'>"
        f"{mode_switch}"
        f"{scene_switch}"
        f"<span class='lang'><a href='{lang_base}lang=en'{en_current}>EN</a>"
        f"<a href='{lang_base}lang=es'{es_current}>ES</a></span>"
        "<span id='costLabel'>USD 0.0000 of 1.00 cap</span>"
        f"<span>{_e(_L('chain_duration'))}: <span id='chainDuration'>00:00</span></span>"
        f"<button class='btn ghost' id='newRunBtn' type='button'>{_e(_L('new_run'))}</button>"
        "</div></div>"
        "<div class='hero'>"
        f"<canvas id='sphereCanvas' role='img' aria-label='{_e(_L('sphere_label'))}'></canvas>"
        "<div class='hero-copy'>"
        f"<p class='hero-brand' aria-hidden='true'><span class='hero-fill'>{_e(BRAND[:2])}</span>"
        f"<span class='hero-outline'>{_e(BRAND[2:])}</span></p>"
        f"<p class='hero-subtitle'>{_e(_L('hero_subtitle'))}</p>"
        f"<h1 id='headline' aria-live='polite'>{_e(_L('headline_start'))}</h1>"
        "<div id='attackerStrip' class='attempts'></div>"
        f"<button class='btn primary run-until' id='runUntilBtn' type='button'>"
        f"{_e(_L('run_until'))}</button>"
        f"{live_off_block}"
        "</div>"
        f"<div class='clockbox'><p id='clockLabel'>{_e(_L('time_to_401'))}</p>"
        "<p id='bigClock'>--:--</p>"
        f"<p class='clock-note'>{_e(_L('real_incident'))}</p></div>"
        "</div></div></header>"
        "<div class='stickybar'><div class='sticky-inner'>"
        f"<span class='sticky-brand'>{_e(BRAND)}</span>"
        f"<span class='sticky-group'><span class='sticky-label' id='stickyClockLabel'>{_e(_L('time_to_401'))}</span>"
        "<span class='sticky-clock' id='stickyClock'>--:--</span></span>"
        f"<span class='sticky-group'><span class='sticky-label'>{_e(_L('sticky_attacker'))}</span>"
        "<span class='sticky-group' id='stickyAttacker'></span></span>"
        f"<span class='sticky-group'><span class='sticky-label'>{_e(_L('sticky_sdk'))}</span>"
        "<span class='sticky-group' id='stickySdk'></span></span>"
        "<span class='sticky-cost' id='stickyCost'>USD 0.0000</span>"
        f"<button class='btn ghost' id='stickyNewRunBtn' type='button'>{_e(_L('new_run'))}</button>"
        "</div></div>"
        "<main class='wrap'>"
        f"<p id='noKeyBox'{no_key_hidden}>{_e(_L('no_key'))}: {_e(_L('no_key_body'))}</p>"
        f"<ol class='steps'>{steps}</ol>"
        f"<p id='sparkOpenRow'>{_e(spark_row)}</p>"
        f"<section><h2>{_e(_L('provenance'))}</h2>"
        + (f"<p class='replay-note'>{_e(prov_note)}</p>" if replay else "")
        + f"<a class='btn secondary' href='{api}/provenance.json'>{_e(_L('export_log'))}</a>"
        "<div class='tablewrap'><table><thead><tr>"
        f"<th>{_e(_L('th_step'))}</th><th>{_e(_L('th_agent'))}</th>"
        f"<th>{_e(_L('th_model'))}</th><th>{_e(_L('th_response'))}</th>"
        f"<th>{_e(_L('th_latency'))}</th><th>{_e(_L('th_in'))}</th>"
        f"<th>{_e(_L('th_out'))}</th><th>{_e(_L('th_cost'))}</th>"
        f"<th>{_e(_L('th_http'))}</th><th>{_e(_L('th_decision'))}</th>"
        "</tr></thead><tbody id='provBody'></tbody></table></div></section>"
        "</main>"
        "<footer class='wrap footer'>"
        f"<p>{_e(_L('footer_meta'))}</p><p>{_e(_L('footer_hack'))}</p>"
        "</footer>"
        f"<script>{script}</script></body></html>"
    )


def render_live_inactive_page(lang: str = "en") -> str:
    lang = lang if lang in T else "en"
    en_current = " aria-current='true'" if lang == "en" else ""
    es_current = " aria-current='true'" if lang == "es" else ""
    return (
        "<!doctype html>\n"
        f"<html lang='{_e(lang)}'><head><meta charset='utf-8'>"
        "<link rel='icon' href='data:,'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_e(BRAND)} — {_e(SUBTITLE)} live</title>"
        f"<style>{_CSS}</style></head><body>"
        "<header class='band'><div class='inner'>"
        "<div class='band-top'>"
        f"<p class='brandline'><strong>{_e(BRAND)}</strong> · {_e(SUBTITLE)}</p>"
        "<div class='band-tools'>"
        f"<nav class='mode-switch'><a href='/'>{_e(_t(lang, 'replay'))}</a>"
        f"<a href='/live' aria-current='true'>{_e(_t(lang, 'live'))}</a></nav>"
        f"<span class='lang'><a href='/live?lang=en'{en_current}>EN</a>"
        f"<a href='/live?lang=es'{es_current}>ES</a></span>"
        "</div></div>"
        f"<h1>{_e(_t(lang, 'activate_title'))}</h1>"
        "</div></header>"
        "<main class='wrap'>"
        f"<p>{_e(_t(lang, 'activate_body'))}</p>"
        "<p><code>make live</code></p>"
        f"<p>{_e(_t(lang, 'no_key'))}: {_e(_t(lang, 'no_key_body'))}</p>"
        "</main>"
        "<footer class='wrap footer'>"
        f"<p>{_e(_t(lang, 'footer_meta'))}</p><p>{_e(_t(lang, 'footer_hack'))}</p>"
        "</footer></body></html>"
    )
