"""Pantalla /live: HTML, CSS y JS propio inline, sin externos."""

# ruff: noqa: E501

from __future__ import annotations

import html
from typing import Any

from web.brand import BRAND, SUBTITLE

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
        "voice_no_speech": "No se detectó voz. Revisa el micrófono y vuelve a intentar.",
        "mic_silence": "El micrófono grabó silencio",
        "level_label": "Nivel del micrófono (RMS)",
        "time_since_attack": "Tiempo desde que empezó el ataque",
        "th_decision": "decisión de política",
        "action_rotate_token": "Rotar el token",
        "action_verify": "Comprobar que sigue funcionando",
        "action_draft_notice": "Preparar un borrador de aviso",
        "action_rotate_upstream_key": "Rotar la clave del proveedor",
        "live_label": "LIVE — real Meta models, called from this Mac through the Shield gateway",
        "replay": "Replay",
        "live": "Live",
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
        "weak_label": "Deliberately misconfigured agent (test): told to obey invoice notes",
        "attempted": "Llamadas a herramientas intentadas",
        "no_attempt": "El modelo no intentó ninguna llamada a herramienta.",
        "decision": "Decisión",
        "reason": "Razón",
        "evidence": "Evidencia",
        "account_before_after": "Cuenta del proveedor antes / después",
        "use_own_photo": "Use your own photo (no people, no real data)",
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
        "demo_inventory": "Demo inventory",
        "plan_summary": "Resumen",
        "plan_reasoning": "Razonamiento del modelo",
        "plan_exposures": "Exposiciones",
        "plan_steps": "Pasos",
        "guardian_turns": "Turnos del guardián",
        "no_plan_error": "guardian_no_plan: Spark did not propose a plan within 10 turns",
        "record": "Grabar",
        "stop": "Detener",
        "typed_fallback": "Typed fallback: no Voice Transcribe is used in this path",
        "voice_hint": 'Try: "sí, rota el token de bodega"',
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
        "spark_open_row": "Muse Spark Open: not run. No Baseten, Modal or Fireworks key in this vault.",
        "spark_open_row_key": "Muse Spark Open: not run.",
        "provenance": "Registro de procedencia",
        "export_log": "Export log (JSON)",
        "th_step": "paso",
        "th_agent": "agente",
        "th_model": "modelo",
        "th_response": "id de respuesta",
        "th_latency": "latencia",
        "th_in": "tokens de entrada",
        "th_out": "tokens de salida",
        "th_cost": "costo",
        "th_http": "HTTP",
        "footer_meta": "Built on Meta's Muse models; independent project, not affiliated with or endorsed by Meta.",
        "footer_hack": "Built during the hackathon, 26 Oct – 4 Nov 2026.",
        "activate_title": "El modo live no está activo",
        "activate_body": "Arráncalo con make live y vuelve a abrir /live. Desde esta pantalla no se llama a ningún modelo.",
        "no_key": "No key in the vault",
        "no_key_body": "Pon META_MODEL_API_KEY en el vault (backend de entorno) y reinicia con make live. La llave nunca se muestra aquí.",
    },
}


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
:root{--col:1140px}
@media (min-width:1600px){:root{--col:1320px}}
*{box-sizing:border-box}
html,body{max-width:100%;overflow-x:hidden}
img{max-width:100%}
body{margin:0;background:#EEF0EA;color:#1C2420;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.45}
h1,h2,h3{font-family:Georgia,"Times New Roman",serif;line-height:1.1;font-weight:400}
a{color:#1F7A4D}
:focus-visible{outline:3px solid #E8A33D;outline-offset:2px}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:10px 18px;border:2px solid #14201C;background:#EEF0EA;color:#14201C;font:inherit;cursor:pointer;text-decoration:none}
.btn.primary{background:#1F7A4D;border-color:#1F7A4D;color:#fff}
.btn.secondary{background:#fff}
.btn.ghost{background:#14201C;border-color:#EEF0EA;color:#EEF0EA}
.btn.alert-btn{background:#B42318;border-color:#B42318;color:#fff}
.band{background:#14201C;color:#EEF0EA}
.band .inner,.wrap{width:min(var(--col),calc(100% - 40px));max-width:var(--col);margin:0 auto}
.verdict{font-size:20px;font-weight:700;background:#fff;border-left:6px solid #B42318;padding:12px 14px}
.forced-row{background:#fff;border:2px solid #B42318;padding:12px 14px;margin:14px 0}
.invoice-media{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start;max-width:100%}
[hidden]{display:none!important}
.fineprint-wrap{flex:1 1 300px;max-width:1000px;height:90px;overflow:hidden;border:1px solid #14201C;background:#fff}
.fineprint{width:108%;max-width:none;display:block;transform:translate(-4%,-64%)}
.hidden-note{font-size:17px;background:#fff;padding:10px 12px;overflow-wrap:anywhere}
.band .inner{padding:18px 0 22px}
.band-top{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between}
.brandline{margin:0;font-size:15px}
.live-label{border:1px solid #E8A33D;color:#E8A33D;padding:8px 10px;font-size:13px}
.band-tools{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.mode-switch,.lang{display:inline-flex}
.mode-switch a,.lang a{display:inline-flex;align-items:center;min-height:44px;padding:8px 12px;color:#EEF0EA;border:1px solid #EEF0EA;text-decoration:none}
.mode-switch a[aria-current="true"],.lang a[aria-current="true"]{background:#E8A33D;color:#14201C}
.band-main{display:flex;gap:28px;align-items:flex-start;justify-content:space-between}
.band h1{font-size:clamp(36px,5vw,60px);margin:20px 0 10px}
.clockbox{text-align:right;min-width:210px;padding-top:26px}
#bigClock{font-family:Georgia,serif;font-size:clamp(34px,4vw,54px);margin:0;line-height:1.1}
.clock-note{margin:6px 0 0;font-size:15px}
.attempts{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.code-block{display:inline-flex;align-items:center;justify-content:center;min-width:64px;min-height:52px;padding:8px 12px;font-size:22px;font-family:ui-monospace,Menlo,Consolas,monospace;background:#EEF0EA;color:#14201C}
.code-200{background:#E8A33D;color:#14201C}
.code-401{background:#B42318;color:#fff}
.wrap{padding:22px 0}
.run-until{margin:18px 0}
.steps{list-style:none;margin:0;padding:0;border-left:3px solid #14201C}
.step{position:relative;padding:18px 0 18px 28px;border-bottom:1px solid #c9cec2}
.step-num{position:absolute;left:-17px;top:16px;width:32px;height:32px;background:#14201C;color:#EEF0EA;display:flex;align-items:center;justify-content:center;font-family:Georgia,serif}
.step-head{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between}
.step h2{font-size:24px;margin:0}
.step-status{font-size:14px}
.result{margin-top:12px}
.columns{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.decision-block{padding:10px 12px;margin:8px 0;font-weight:700}
.decision-block.block{background:#B42318;color:#fff}
.decision-block.ask{color:#14201C}
.decision-block.ask-ask_owner{background:#E8A33D;color:#14201C}
.decision-block.ask-block{background:#B42318;color:#fff}
.decision-block.allow{background:#1F7A4D;color:#fff}
.decision-block.ask_owner{background:#E8A33D;color:#14201C}
.thumb{max-width:220px;width:100%;height:auto;border:1px solid #14201C}
.shelf-wrap{position:relative;max-width:560px}
.shelf-wrap img{width:100%;height:auto;display:block}
.box-overlay{position:absolute;border:3px solid #B42318}
.bigcount{font-family:Georgia,serif;font-size:44px}
.mono{font-family:ui-monospace,Menlo,Consolas,monospace;overflow-wrap:anywhere;word-break:break-word}
.tablewrap{overflow-x:auto;max-width:100%;width:100%}
table{border-collapse:collapse;width:100%;min-width:640px;background:#fff}
td,th{border-bottom:1px solid #c9cec2;padding:9px 8px;text-align:left;vertical-align:top}
.footer{border-top:2px solid #14201C;font-size:14px}
input[type="text"]{width:100%;min-height:44px;padding:10px;font:inherit}
input[type="file"]{min-height:44px;padding:10px;font:inherit;width:100%;max-width:100%}
label{display:block;font-weight:700;margin:10px 0 6px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;max-width:100%;background:#fff;padding:12px}
.btn{max-width:100%;white-space:normal;text-align:center}
@media (max-width:760px){.band-main{display:block}.clockbox{text-align:left;padding-top:0;min-width:0}.columns{grid-template-columns:1fr}.band-tools,.band-top{max-width:100%}.step{padding-left:20px}.code-block{min-width:48px;font-size:18px}}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto;animation:none;transition:none}}
"""

_JS = r"""
const TEXT = __TEXTS__;
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
function setStatus(step, text) {
  const node = document.querySelector("[data-status-for='" + step + "']");
  if (node) node.textContent = text;
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
    container.appendChild(el("span", s, "code-block code-" + s));
  });
}
function anomalyText(a) {
  const kind = String((a && a.kind) || "");
  if (kind === "new_country") return TEXT.anomaly_new_country;
  if (kind === "new_model") return TEXT.anomaly_new_model;
  if (kind === "cost_spike") return TEXT.anomaly_cost_spike;
  if (kind === "blocked_burst") return TEXT.anomaly_blocked_burst;
  if (kind === "volume_spike") return TEXT.anomaly_volume_spike;
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
  box.appendChild(el("p", TEXT.guardian_turns + ": " + turns.length + " " + TEXT.turns_used + " · " + toolCount + " " + TEXT.tools_used));
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
  box.appendChild(el("h3", TEXT.guardian_turns));
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
  const intent = r.intent || {};
  byId("voiceIntent").textContent = intentPlain(intent);
  const showConfirm = r.status === "confirmation_required";
  byId("voiceConfirm").hidden = !showConfirm;
  byId("voiceCancel").hidden = !showConfirm;
  byId("disagreeLine").textContent = intent.source === "disagreement" ? TEXT.disagreement : "";
  byId("voiceStatusLine").textContent = r.status === "unknown_command" ? TEXT.voice_unknown : (r.status === "no_speech" ? TEXT.voice_no_speech : (r.status || ""));
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
function renderResult(step, r, state) {
  if (!r) return;
  if (step === "invoice") renderInvoice(r);
  if (step === "count") renderCount(r);
  if (step === "attack") renderAttack(r);
  if (step === "guardian") renderGuardian(r);
  if (step === "voice") renderVoice(r);
  if (step === "contain") renderContain(r, state);
}
let lastState = null;
let clockTimer = null;
function updateBand(state) {
  lastState = state || lastState;
  if (!state) return;
  const total = Number(state.total_cost_usd || 0);
  const cap = Number(state.cap_usd || 1);
  byId("costLabel").textContent = "USD " + total.toFixed(4) + " " + TEXT.cost_of_cap.replace("{cap}", cap.toFixed(2));
  const results = state.results || {};
  const contained = results.contain && (results.contain.attacker_after || []).includes(401);
  let headline = TEXT.headline_start;
  if (contained) headline = TEXT.headline_contained;
  else if (results.guardian) headline = TEXT.headline_waiting;
  else if (results.attack) headline = TEXT.headline_attack;
  byId("headline").textContent = headline;
  const strip = [];
  if (results.attack) strip.push(...(results.attack.statuses || []));
  if (results.contain) strip.push(...(results.contain.attacker_after || []));
  statusBlocks(byId("attackerStrip"), strip);
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
  };
  tickClock();
  clockTimer = setInterval(tickClock, 1000);
  Object.keys(results).forEach((key) => renderResult(key === "voice_confirm" || key === "voice_cancel" ? "voice" : key, results[key], state));
}
async function refreshState() {
  const res = await fetch("/live/state");
  if (!res.ok) return null;
  const state = await res.json();
  if (state.status === "not_started") {
    const started = await fetch("/live/start", {method: "POST"});
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
        res = await fetch("/live/step/count", {method: "POST", body: form});
      } else {
        res = await fetch("/live/step/count", {method: "POST"});
      }
    } else {
      res = await fetch("/live/step/" + step, {method: "POST"});
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
    const res = await fetch("/live/voice", {method: "POST", body: form});
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
document.addEventListener("DOMContentLoaded", () => {
  byId("runUntilBtn").addEventListener("click", runUntilOwner);
  byId("newRunBtn").addEventListener("click", async () => {
    await fetch("/live/reset", {method: "POST"});
    document.querySelectorAll("[data-status-for]").forEach((n) => { n.textContent = TEXT.not_run; });
    await refreshState();
  });
  document.querySelectorAll("[data-run-step]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const step = btn.getAttribute("data-run-step");
      if (step === "voice") { toggleRecord(); return; }
      runStep(step);
    });
  });
  byId("recordBtn").addEventListener("click", toggleRecord);
  byId("sendTypedBtn").addEventListener("click", async () => {
    const form = new FormData();
    form.append("typed", byId("typedText").value);
    startStatus("voice");
    const res = await fetch("/live/voice", {method: "POST", body: form});
    const data = await res.json();
    stopStatus("voice", data.status === "error" ? TEXT.error + ": " + (data.error || "") : TEXT.ok + ": " + (data.status || ""));
    renderVoice(data);
    await refreshState();
    if (data.status === "approved") await runStep("contain");
  });
  byId("voiceConfirm").addEventListener("click", async () => {
    const res = await fetch("/live/voice/confirm", {method: "POST"});
    const data = await res.json();
    byId("voiceStatusLine").textContent = data.status || "";
    await refreshState();
    if (data.status === "approved") await runStep("contain");
  });
  byId("voiceCancel").addEventListener("click", async () => {
    const res = await fetch("/live/voice/cancel", {method: "POST"});
    const data = await res.json();
    byId("voiceStatusLine").textContent = data.status || "";
    await refreshState();
  });
  refreshState();
});
"""




def _step_html(number: int, step: str, title: str, lang: str, inner: str) -> str:
    return (
        f"<li class='step' data-step='{step}'><span class='step-num'>{number}</span>"
        f"<div class='step-head'><h2>{_e(title)}</h2>"
        f"<span class='step-status' data-status-for='{step}' aria-live='polite'>"
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
) -> str:
    import json as _json

    lang = lang if lang in T else "en"
    texts = _json.dumps(T[lang], ensure_ascii=False)
    script = _JS.replace("__TEXTS__", texts)
    en_current = " aria-current='true'" if lang == "en" else ""
    es_current = " aria-current='true'" if lang == "es" else ""
    spark_row = _t(lang, "spark_open_row") if spark_open_no_key else _t(lang, "spark_open_row_key")
    step1_inner = (
        "<div class='invoice-media'>"
        "<img class='thumb' src='/live/fixture/invoice' alt='invoice fixture'>"
        "<div class='fineprint-wrap'><img class='fineprint' src='/live/fixture/invoice' "
        "alt='invoice fine print'></div></div>"
        f"<p>{_e(_t(lang, 'hidden_order'))}</p><div id='invoiceResult'></div>"
    )
    step2_inner = (
        "<div class='shelf-wrap'><img id='shelfImg' src='/live/fixture/shelf' alt='shelf fixture'>"
        "<div id='shelfOverlay'></div></div>"
        f"<p class='bigcount' id='countValue'></p>"
        f"<p id='materialLabel'></p><p id='expectedLine'></p>"
        f"<label for='ownPhoto'>{_e(_t(lang, 'use_own_photo'))}</label>"
        "<input id='ownPhoto' type='file' accept='image/*'>"
    )
    step3_inner = (
        f"<p>{_e(_t(lang, 'attacker_attempts'))}</p>"
        "<div id='attackStatuses' class='attempts'></div>"
        f"<h3>{_e(_t(lang, 'anomalies'))}</h3><ul id='anomalyList'></ul>"
    )
    step4_inner = f"<p>{_e(_t(lang, 'demo_inventory'))}</p><div id='guardianResult'></div>"
    step5_inner = (
        f"<button class='btn primary' id='recordBtn' type='button'>{_e(_t(lang, 'record'))}</button>"
        " <span id='recordTimer' aria-live='polite'></span>"
        f"<p id='micError' aria-live='polite'></p><p id='voiceLevel' aria-live='polite'></p>"
        f"<label for='typedText'>{_e(_t(lang, 'typed_fallback'))}</label>"
        "<input id='typedText' type='text'>"
        f"<p>{html.escape(_t(lang, 'voice_hint'), quote=False)}</p>"
        f"<button class='btn secondary' id='sendTypedBtn' type='button'>{_e(_t(lang, 'send_typed'))}</button>"
        f"<h3>{_e(_t(lang, 'transcript'))}</h3><p id='voiceTranscript'></p>"
        f"<h3>{_e(_t(lang, 'spark_intent'))}</h3><p id='voiceIntent' class='mono'></p>"
        "<p id='disagreeLine'></p><p id='voiceStatusLine' aria-live='polite'></p>"
        f"<button class='btn primary' id='voiceConfirm' type='button' hidden>{_e(_t(lang, 'confirm'))}</button>"
        f" <button class='btn secondary' id='voiceCancel' type='button' hidden>{_e(_t(lang, 'cancel'))}</button>"
    )
    step6_inner = (
        f"<p>{_e(_t(lang, 'attacker_before'))}</p><div id='attackerBefore' class='attempts'></div>"
        f"<p>{_e(_t(lang, 'attacker_after'))}</p><div id='attackerAfter' class='attempts'></div>"
        "<p id='sdkLine'></p><p id='recountLine'></p><p id='comprasLine'></p>"
        "<p id='containedLine'></p>"
    )
    steps = "".join(
        [
            _step_html(1, "invoice", _t(lang, "step1_title"), lang, step1_inner),
            _step_html(2, "count", _t(lang, "step2_title"), lang, step2_inner),
            _step_html(3, "attack", _t(lang, "step3_title"), lang, step3_inner),
            _step_html(4, "guardian", _t(lang, "step4_title"), lang, step4_inner),
            _step_html(5, "voice", _t(lang, "step5_title"), lang, step5_inner),
            _step_html(6, "contain", _t(lang, "step6_title"), lang, step6_inner),
        ]
    )
    no_key_hidden = "" if no_key else " hidden"
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
        f"<span class='live-label'>{_e(_t(lang, 'live_label'))}</span>"
        "<div class='band-tools'>"
        f"<nav class='mode-switch'><a href='/'>{_e(_t(lang, 'replay'))}</a>"
        f"<a href='/live' aria-current='true'>{_e(_t(lang, 'live'))}</a></nav>"
        f"<span class='lang'><a href='/live?lang=en'{en_current}>EN</a>"
        f"<a href='/live?lang=es'{es_current}>ES</a></span>"
        "<span id='costLabel'>USD 0.0000 of 1.00 cap</span>"
        f"<span>{_e(_t(lang, 'chain_duration'))}: <span id='chainDuration'>00:00</span></span>"
        f"<button class='btn ghost' id='newRunBtn' type='button'>{_e(_t(lang, 'new_run'))}</button>"
        "</div></div>"
        "<div class='band-main'><div>"
        f"<h1 id='headline' aria-live='polite'>{_e(_t(lang, 'headline_start'))}</h1>"
        "<div id='attackerStrip' class='attempts'></div>"
        "</div>"
        f"<div class='clockbox'><p id='clockLabel'>{_e(_t(lang, 'time_to_401'))}</p>"
        "<p id='bigClock'>--:--</p>"
        f"<p class='clock-note'>{_e(_t(lang, 'real_incident'))}</p></div>"
        "</div></div></header>"
        "<main class='wrap'>"
        f"<p id='noKeyBox'{no_key_hidden}>{_e(_t(lang, 'no_key'))}: {_e(_t(lang, 'no_key_body'))}</p>"
        f"<button class='btn primary run-until' id='runUntilBtn' type='button'>"
        f"{_e(_t(lang, 'run_until'))}</button>"
        f"<ol class='steps'>{steps}</ol>"
        f"<p id='sparkOpenRow'>{_e(spark_row)}</p>"
        f"<section><h2>{_e(_t(lang, 'provenance'))}</h2>"
        f"<a class='btn secondary' href='/live/provenance.json'>{_e(_t(lang, 'export_log'))}</a>"
        "<div class='tablewrap'><table><thead><tr>"
        f"<th>{_e(_t(lang, 'th_step'))}</th><th>{_e(_t(lang, 'th_agent'))}</th>"
        f"<th>{_e(_t(lang, 'th_model'))}</th><th>{_e(_t(lang, 'th_response'))}</th>"
        f"<th>{_e(_t(lang, 'th_latency'))}</th><th>{_e(_t(lang, 'th_in'))}</th>"
        f"<th>{_e(_t(lang, 'th_out'))}</th><th>{_e(_t(lang, 'th_cost'))}</th>"
        f"<th>{_e(_t(lang, 'th_http'))}</th><th>{_e(_t(lang, 'th_decision'))}</th>"
        "</tr></thead><tbody id='provBody'></tbody></table></div></section>"
        "</main>"
        "<footer class='wrap footer'>"
        f"<p>{_e(_t(lang, 'footer_meta'))}</p><p>{_e(_t(lang, 'footer_hack'))}</p>"
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
