"""Vista «Surveillance»: cámaras reales de Clara del Rey (Madrid) con SAM 3.1.

La comparten la escena Sentinel (sección al pie) y la vista dedicada
``/?scene=surveillance`` (1920×1080 sin scroll, para el video). Todo número
sale de ``web.sentinel_witness`` (observaciones grabadas en
``SHIELD_WITNESS_DIR`` y el eval grabado del repo); la animación «Scan the
site now» solo recorre datos ya cargados: no llama a ningún modelo.
"""

# ruff: noqa: E501

from __future__ import annotations

import html
import json
from typing import Any

from web.brand import BRAND, SUBTITLE, brand_mark_html, favicon_href
from web.sentinel_witness import surveillance_state

SV_T: dict[str, dict[str, str]] = {
    "en": {
        "sv_title": "Surveillance · real cameras, Clara del Rey (Madrid)",
        "sv_sub": "Meta's SAM 3.1 reads real camera frames from our site; every person is covered before a frame is shown. Each card is one security application with its real, redacted image and its real metric.",
        "sv_ribbon": "{cams} real cameras · {frames} real frames · every person redacted before display · {models}",
        "sv_eval_head": "Measured accuracy · {n} labeled real frames · {model} · eval {date}:",
        "sv_eval_pending": "Measured accuracy: pending (no recorded eval).",
        "sv_presence": "presence vs empty {ok}/{n} (precision {p}, recall {r})",
        "sv_count": "people count exact {ok}/{n}, within ±1 {w1}/{n}",
        "sv_perfect": "{rooms}: {ok}/{n} exact",
        "sv_other": "{room}: {ok}/{n} exact, {w1}/{n} within ±1",
        "sv_per_frame": " per frame",
        "sv_occupancy": "Occupancy by room",
        "sv_after_hours": "After-hours intrusion",
        "sv_stock_watch": "Stock watch · storeroom",
        "sv_cash_desk": "Unattended cash desk",
        "sv_security_log": "Spark security log",
        "sv_how_occupancy": "SAM 3.1 counts the people in each room, frame by frame.",
        "sv_how_after_hours": "Outside opening hours: anyone on camera is an alert; nobody is all clear.",
        "sv_how_stock_watch": "SAM 3.1 counts the boxes; a drop out of hours raises a possible-theft alert.",
        "sv_how_cash_desk": "Nobody at the till while the POS opens the drawer = irregularity.",
        "sv_how_security_log": "Muse Spark writes the shift's security report reading only redacted frames and the counts.",
        "sv_st_live": "LIVE", "sv_st_all_clear": "ALL CLEAR", "sv_st_alert": "ALERT",
        "sv_st_ok": "OK", "sv_st_pending": "PENDING", "sv_st_expected": "EXPECTED",
        "sv_simulated": "POS event simulated · camera and count are real",
        "sv_pending_long": "pending — no data from the cameras yet",
        "sv_alt": "Real camera frame, people covered",
        "sv_person": "person", "sv_people": "people",
        "sv_frames": "{n} frames analyzed",
        "sv_live_label": "real camera, live capture",
        "sv_rec_label": "real camera, recorded {hhmm} · Clara del Rey, Madrid · {n} people ({model})",
        "sv_verified": "human-verified empty",
        "sv_blurred": "no person boxes, so the whole frame is blurred (privacy default)",
        "sv_ah_clear": "{rooms} at {hhmm}: 0 people in {e}/{t} frames → all clear",
        "sv_ah_alert": "{room} at {hhmm}: {n} people out of hours → alert",
        "sv_engine": "Autopilot rule on this real frame: a remote defrost here is flagged {rule} → the owner decides.",
        "sv_scan": "Scan the site now",
        "sv_scanning": "Scanning…",
        "sv_scan_note": "Replays the recorded frames and counts — no model is called.",
        "sv_back": "← Sentinel",
        "sv_link": "Real cameras →",
        "sv_page_label": "REAL CAMERAS — recorded frames from our site, people redacted",
        "scene": "Scene",
        "footer_meta": "Built on Meta's models (SAM 3.1, Muse Spark); independent project, not affiliated with or endorsed by Meta.",
    },
    "es": {
        "sv_title": "Vigilancia · cámaras reales, Clara del Rey (Madrid)",
        "sv_sub": "SAM 3.1 de Meta lee cuadros reales de nuestras cámaras; cada persona queda tapada antes de mostrar un cuadro. Cada tarjeta es una aplicación de seguridad con su imagen real redactada y su métrica real.",
        "sv_ribbon": "{cams} cámaras reales · {frames} cuadros reales · cada persona tapada antes de mostrarse · {models}",
        "sv_eval_head": "Precisión medida · {n} cuadros reales etiquetados · {model} · eval {date}:",
        "sv_eval_pending": "Precisión medida: pendiente (no hay eval grabado).",
        "sv_presence": "presencia vs vacío {ok}/{n} (precisión {p}, recall {r})",
        "sv_count": "conteo de personas exacto {ok}/{n}, a ±1 {w1}/{n}",
        "sv_perfect": "{rooms}: {ok}/{n} exactos",
        "sv_other": "{room}: {ok}/{n} exactos, {w1}/{n} a ±1",
        "sv_per_frame": " por cuadro",
        "sv_occupancy": "Ocupación por sala",
        "sv_after_hours": "Intrusión fuera de horario",
        "sv_stock_watch": "Vigilancia de stock · almacén",
        "sv_cash_desk": "Caja desatendida",
        "sv_security_log": "Parte de seguridad de Spark",
        "sv_how_occupancy": "SAM 3.1 cuenta las personas de cada sala, cuadro a cuadro.",
        "sv_how_after_hours": "Fuera del horario de apertura: cualquiera en cámara es alerta; nadie es todo en orden.",
        "sv_how_stock_watch": "SAM 3.1 cuenta las cajas; una caída fuera de horario es alerta de posible robo.",
        "sv_how_cash_desk": "Nadie en la caja mientras el POS abre el cajón = irregularidad.",
        "sv_how_security_log": "Muse Spark redacta el parte del turno leyendo solo cuadros redactados y los conteos.",
        "sv_st_live": "EN VIVO", "sv_st_all_clear": "TODO EN ORDEN", "sv_st_alert": "ALERTA",
        "sv_st_ok": "OK", "sv_st_pending": "PENDIENTE", "sv_st_expected": "ESPERADO",
        "sv_simulated": "evento POS simulado · cámara y conteo reales",
        "sv_pending_long": "pendiente — aún no hay datos de las cámaras",
        "sv_alt": "Cuadro real de cámara, personas tapadas",
        "sv_person": "persona", "sv_people": "personas",
        "sv_frames": "{n} cuadros analizados",
        "sv_live_label": "cámara real, captura en vivo",
        "sv_rec_label": "cámara real, grabación de las {hhmm} · Clara del Rey, Madrid · {n} personas ({model})",
        "sv_verified": "vacío verificado por una persona",
        "sv_blurred": "sin cajas de personas, el cuadro entero va difuminado (privacidad por defecto)",
        "sv_ah_clear": "{rooms} a las {hhmm}: 0 personas en {e}/{t} cuadros → todo en orden",
        "sv_ah_alert": "{room} a las {hhmm}: {n} personas fuera de horario → alerta",
        "sv_engine": "Regla del autopiloto sobre este cuadro real: un deshielo remoto aquí se marca {rule} → decide el dueño.",
        "sv_scan": "Escanear el local ahora",
        "sv_scanning": "Escaneando…",
        "sv_scan_note": "Repite los cuadros y conteos grabados: no se llama a ningún modelo.",
        "sv_back": "← Sentinel",
        "sv_link": "Cámaras reales →",
        "sv_page_label": "CÁMARAS REALES — cuadros grabados en nuestro local, personas tapadas",
        "scene": "Escena",
        "footer_meta": "Construido sobre modelos de Meta (SAM 3.1, Muse Spark); proyecto independiente, sin afiliación ni respaldo de Meta.",
    },
}

SV_CSS = """
.w-frame{position:relative;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:var(--sunk);aspect-ratio:16/9}
.w-frame img{display:block;width:100%;height:100%;object-fit:cover}
.w-frame .scanline{position:absolute;left:0;right:0;top:0;height:3px;background:#efa83a;box-shadow:0 0 18px 6px rgba(239,168,58,.55);opacity:0;pointer-events:none}
.sv-card.sv-scan .scanline{animation:svsweep 1.25s linear 1}
@keyframes svsweep{0%{top:0;opacity:1}92%{opacity:1}100%{top:100%;opacity:0}}
.sv-card{transition:opacity .35s ease,transform .35s ease}
.surv-grid.sv-armed .sv-card.sv-wait{opacity:.12;transform:scale(.985)}
.surv{margin:18px 0 10px;border-top:1px solid var(--line);padding-top:16px}
.surv-title{margin:0;font-size:26px}.surv-sub{margin:4px 0 8px;color:var(--muted)}
.surv-ribbon{margin:0 0 8px;color:var(--warn-text);font-weight:650;font-size:15px}
.surv-ribbon b{font-variant-numeric:tabular-nums}
.surv-eval{margin:0 0 12px;padding:10px 14px;border:1px solid rgba(54,179,126,.4);border-radius:8px;background:rgba(54,179,126,.07);font-size:15px}
.surv-eval b{color:var(--ok-text)}
.surv-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:14px}
.sv-card{grid-column:span 2;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:12px 14px;display:flex;flex-direction:column;gap:6px;min-width:0}
.sv-card.sv-occupancy,.sv-card.sv-after_hours{grid-column:span 3}
.sv-card p{margin:0}.sv-head{display:flex;gap:10px;align-items:center;justify-content:space-between}
.sv-head h3{margin:0;font-size:18px}
.sv-chip{font-size:12px;font-weight:800;letter-spacing:.04em;padding:2px 9px;border-radius:6px;border:1px solid var(--line-strong);color:var(--muted);white-space:nowrap}
.sv-card[data-status="live"] .sv-chip{color:#ffaaa3;border-color:rgba(229,83,75,.55);background:rgba(229,83,75,.12)}
.sv-card[data-status="all_clear"] .sv-chip,.sv-card[data-status="ok"] .sv-chip,.sv-card[data-status="expected"] .sv-chip{color:var(--ok-text);border-color:rgba(54,179,126,.55);background:rgba(54,179,126,.12)}
.sv-card[data-status="alert"]{border-color:rgba(229,83,75,.7)}.sv-card[data-status="alert"] .sv-chip{color:#fff;background:var(--bad);border-color:var(--bad)}
.sv-card[data-status="pending"]{opacity:.8}
.sv-pending{border:1px dashed var(--line-strong);border-radius:8px;padding:28px 12px;text-align:center;color:var(--muted);font-size:14px}
.sv-rooms{list-style:none;margin:4px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:8px}
.sv-rooms li{display:flex;gap:8px;align-items:baseline;background:var(--sunk);border:1px solid var(--line);border-radius:8px;padding:5px 10px;cursor:pointer}
.sv-rooms li[aria-current="true"]{border-color:#efa83a}
.sv-rooms b{color:var(--ok-text);font-size:18px;font-variant-numeric:tabular-nums}
.sv-metric{font-weight:600;font-size:15px}.sv-big{font-weight:800;font-size:20px;color:var(--warn-text)}
.sv-card[data-status="alert"] .sv-big{color:var(--bad-text)}.sv-time{font-weight:600;font-size:14px;color:var(--muted)}
.sv-log ul{margin:0;padding-left:18px}.sv-log li{margin:2px 0}.sv-log-title{font-weight:800;margin:0 0 4px}
.sv-log li.sv-action{list-style:none;margin:6px 0 2px -18px;padding:6px 10px;border-left:4px solid #efa83a;background:rgba(239,168,58,.12);color:var(--warn-text);font-weight:700;border-radius:4px}
.sv-sim{color:var(--warn-text);font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}.sv-src{color:var(--warn-text);font-size:14px}
.sv-proof{color:var(--muted);font-size:13px}.sv-log{white-space:pre-wrap;font-size:14px;background:var(--sunk);border-radius:8px;padding:8px 10px;overflow:auto}
@media (prefers-reduced-motion:reduce){.sv-card.sv-scan .scanline{animation:none}.sv-card{transition:none}}
"""

# Requiere en la página: TEXT, el(), byId(), clear().
SV_JS = r"""
function fill(tpl, vals) { return String(tpl || "").replace(/\{(\w+)\}/g, (m, k) => (k in vals ? String(vals[k]) : m)); }
function fx(v) { return v == null ? "—" : Number(v).toFixed(2); }
function fmtMs(ms) { return ms >= 10000 ? Math.round(ms / 1000) + " s" : Math.round(ms) + " ms"; }
function fmtProof(c) { return [c.model, c.response_id_short ? c.response_id_short + (c.response_count > 1 ? " ×" + c.response_count : "") : "", c.latency_ms != null ? fmtMs(c.latency_ms) : "", c.cost_usd != null ? "USD " + Number(c.cost_usd).toFixed(4) : ""].filter(Boolean).join(" · "); }
function L(c, k) { return TEXT.lang_code === "es" ? (c[k + "_es"] || c[k + "_en"] || c[k]) : (c[k + "_en"] || c[k]); }
function num(n) { const b = el("b", n); b.dataset.count = String(n); return b; }
function filled(parent, tpl, vals, counted) {
  // Plantilla con {k}; las claves de «counted» van en <b data-count> para la animación.
  String(tpl || "").split(/(\{\w+\})/).forEach((part) => {
    const m = part.match(/^\{(\w+)\}$/);
    if (!m) { if (part) parent.appendChild(document.createTextNode(part)); return; }
    const v = vals[m[1]];
    if (counted && counted.includes(m[1]) && typeof v === "number") parent.appendChild(num(v));
    else parent.appendChild(document.createTextNode(v == null ? part : String(v)));
  });
  return parent;
}
function renderEval(ev) {
  const p = byId("svEval"); if (!p) return; clear(p);
  if (!ev) { p.textContent = TEXT.sv_eval_pending; return; }
  const parts = [fill(TEXT.sv_presence, {ok: ev.presence_ok, n: ev.presence_n, p: fx(ev.presence_precision), r: fx(ev.presence_recall)})];
  if (ev.count_n) parts.push(fill(TEXT.sv_count, {ok: ev.exact, w1: ev.within_1, n: ev.count_n}));
  const pf = ev.perfect || {};
  if (pf.n) parts.push(fill(TEXT.sv_perfect, {rooms: (TEXT.lang_code === "es" ? pf.rooms_es : pf.rooms_en).join(", "), ok: pf.exact, n: pf.n}));
  (ev.others || []).forEach((o) => parts.push(fill(TEXT.sv_other, {room: L(o, "room"), ok: o.exact, w1: o.within_1, n: o.n})));
  if (ev.latency_p50_ms != null) parts.push("p50 " + Math.round(ev.latency_p50_ms) + " ms");
  if (ev.cost_per_frame_usd != null) parts.push("USD " + Number(ev.cost_per_frame_usd).toFixed(4) + TEXT.sv_per_frame);
  p.appendChild(el("b", fill(TEXT.sv_eval_head, {n: ev.frames, model: ev.model, date: ev.run_date}) + " "));
  p.appendChild(el("span", parts.join(" · ")));
}
function renderRibbon(stats) {
  const r = byId("svRibbon"); if (!r) return; clear(r);
  if (!stats || !stats.frames) { r.hidden = true; return; }
  r.hidden = false;
  filled(r, TEXT.sv_ribbon, {cams: stats.cameras, frames: stats.frames, models: (stats.models || []).join(" + ")}, ["cams", "frames"]);
}
function frame(src) {
  const f = el("div", null, "w-frame"); const img = el("img"); img.src = src; img.alt = TEXT.sv_alt; img.decoding = "async";
  f.appendChild(img); f.appendChild(el("i", null, "scanline")); return f;
}
function renderSurveillance(sv) {
  renderEval(sv.eval); renderRibbon(sv.stats);
  const grid = byId("svGrid"); if (!grid) return; clear(grid);
  (sv.cards || []).forEach((c) => {
    const card = el("article", null, "sv-card sv-" + c.key); card.dataset.status = c.status; card.dataset.key = c.key;
    const head = el("div", null, "sv-head");
    head.appendChild(el("h3", TEXT["sv_" + c.key]));
    head.appendChild(el("span", TEXT["sv_st_" + c.status] || c.status, "sv-chip"));
    card.appendChild(head);
    card.appendChild(el("p", TEXT["sv_how_" + c.key], "hint sv-how"));
    if (c.image) card.appendChild(frame(c.image));
    else if (c.status === "pending") card.appendChild(el("div", TEXT.sv_pending_long, "sv-pending"));
    if (c.key === "occupancy" && c.rooms) {
      const ul = el("ul", null, "sv-rooms");
      const src = el("p", null, "sv-src");
      const showRoom = (r, li) => {
        const img = card.querySelector(".w-frame img"); if (img && r.image) img.src = r.image;
        ul.querySelectorAll("li").forEach((x) => x.removeAttribute("aria-current")); if (li) li.setAttribute("aria-current", "true");
        src.textContent = TEXT.sv_live_label + " · " + L(r, "room") + (r.hhmm ? " · " + r.hhmm : "") + " · " + r.people + " " + (r.people === 1 ? TEXT.sv_person : TEXT.sv_people) + " · " + fill(TEXT.sv_frames, {n: r.frames}) + (r.people === 0 ? " · " + TEXT.sv_blurred : "");
      };
      c.rooms.forEach((r) => {
        const li = el("li"); li.appendChild(el("span", L(r, "room"))); li.appendChild(num(r.people));
        li.appendChild(el("span", r.people === 1 ? TEXT.sv_person : TEXT.sv_people, "hint"));
        if (r.hhmm) li.appendChild(el("span", r.hhmm, "hint mono"));
        li.addEventListener("click", () => showRoom(r, li)); li._show = () => showRoom(r, li);
        ul.appendChild(li);
      });
      card.appendChild(ul); card.appendChild(src);
      const last = c.rooms.find((r) => r.room_en === c.image_room_en) || c.rooms[c.rooms.length - 1];
      const defLi = ul.children[c.rooms.indexOf(last)]; if (defLi) defLi.dataset.default = "1";
      showRoom(last, defLi);
    } else if (c.key === "after_hours" && c.status !== "pending") {
      const rooms = (c.rooms || []).map((r) => L(r, "room")).join(", ") || L(c, "room");
      const m = c.status === "alert" ? TEXT.sv_ah_alert : TEXT.sv_ah_clear;
      card.appendChild(filled(el("p", null, "sv-metric"), m, {rooms: rooms, room: L(c, "room"), hhmm: c.recorded_hhmm, n: c.people, e: c.frames_empty, t: c.frames}, ["n", "e", "t"]));
      card.appendChild(el("p", fill(TEXT.sv_rec_label, {hhmm: c.recorded_hhmm, n: c.people, model: c.model}) + (c.human_verified ? " · " + TEXT.sv_verified : ""), "sv-src"));
      if (c.engine && (c.engine.findings || []).length) card.appendChild(el("p", fill(TEXT.sv_engine, {rule: c.engine.findings.join(", ")}), "hint sv-engine"));
    } else if (c.status !== "pending") {
      if (c.metric) { const big = el("p", L(c, "metric"), "sv-big"); if (c.hhmm) big.appendChild(el("span", " · " + c.hhmm, "sv-time")); card.appendChild(big); }
      const summary = L(c, "summary"); if (summary) card.appendChild(el("p", summary, "sv-metric"));
      if (c.simulated) card.appendChild(el("p", TEXT.sv_simulated, "sv-sim"));
      const lines = TEXT.lang_code === "es" ? (c.lines_es || c.lines_en) : c.lines_en;
      if (lines && lines.length) {
        const box = el("div", null, "sv-log"); const ul = el("ul");
        lines.forEach((raw, i) => {
          const t = String(raw).replace(/^\s*(?:[-*•]|\d+[.)])\s+/, "");
          const isTitle = /^#+\s*/.test(raw) || (i === 0 && lines.length > 2 && /:\s*$/.test(t));
          if (isTitle) { box.appendChild(el("p", t.replace(/^#+\s*/, ""), "sv-log-title")); return; }
          const li = el("li", t);
          if (/^(action needed|acción (necesaria|requerida)|accion (necesaria|requerida))\s*:/i.test(t)) li.className = "sv-action";
          ul.appendChild(li);
        });
        box.appendChild(ul); card.appendChild(box);
      }
    }
    const proof = fmtProof(c); if (proof && c.status !== "pending") card.appendChild(el("p", proof, "sv-proof mono"));
    grid.appendChild(card);
  });
}
function reducedMotion() { return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches; }
function countUp(root, ms) {
  root.querySelectorAll("[data-count]").forEach((b) => {
    const target = Number(b.dataset.count); if (!isFinite(target)) return;
    const t0 = performance.now();
    const step = (now) => { const k = Math.min(1, (now - t0) / ms); b.textContent = String(Math.round(target * k)); if (k < 1) requestAnimationFrame(step); };
    b.textContent = "0"; requestAnimationFrame(step);
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function scanSite(btn) {
  // ~8 s: la cinta cuenta, luego cada tarjeta se «escanea» con los datos ya grabados.
  const grid = byId("svGrid"); if (!grid) return;
  if (reducedMotion()) return;
  if (btn) { btn.disabled = true; btn.textContent = TEXT.sv_scanning; }
  const cards = Array.from(grid.querySelectorAll(".sv-card"));
  cards.forEach((c) => { c.classList.add("sv-wait"); c.classList.remove("sv-scan"); c.querySelectorAll("[data-count]").forEach((b) => { b.textContent = "0"; }); });
  grid.classList.add("sv-armed");
  const ribbon = byId("svRibbon"); if (ribbon) countUp(ribbon, 900);
  await sleep(700);
  for (const card of cards) {
    card.classList.remove("sv-wait");
    const lis = Array.from(card.querySelectorAll(".sv-rooms li"));
    if (lis.length) {
      // Recorre las cámaras: cada sala con su cuadro redactado y su conteo.
      for (const li of lis) {
        li._show(); card.classList.remove("sv-scan"); void card.offsetWidth; card.classList.add("sv-scan");
        countUp(li, 450); await sleep(Math.max(380, Math.floor(2800 / lis.length)));
      }
      const def = lis.find((li) => li.dataset.default === "1"); if (def) def._show();
    } else {
      card.classList.remove("sv-scan"); void card.offsetWidth; card.classList.add("sv-scan");
      countUp(card, 900); await sleep(1100);
    }
  }
  grid.classList.remove("sv-armed");
  if (btn) { btn.disabled = false; btn.textContent = TEXT.sv_scan; }
}
"""


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def sv_text(lang: str) -> dict[str, str]:
    return dict(SV_T.get(lang, SV_T["en"]))


_PAGE_CSS = """
:root{--bg:#0a0d12;--surface:#10151c;--sunk:#0c1016;--line:#212935;--line-strong:#2f3946;--text:#e8ecf2;--muted:#9aa5b4;--ok:#36b37e;--ok-text:#7fe0b4;--bad:#e5534b;--bad-text:#ffaaa3;--warn:#efa83a;--warn-text:#ffd28a;--sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;--mono:ui-monospace,Menlo,Consolas,monospace}
*{box-sizing:border-box}[hidden]{display:none!important}
html,body{margin:0;background:var(--bg);color:var(--text);font-family:var(--sans);font-size:16px;line-height:1.4}
a{color:#ffd28a}.hint{color:var(--muted);font-size:13px}.mono{font-family:var(--mono)}
.page{height:100vh;min-height:760px;display:flex;flex-direction:column;padding:12px 24px 10px;gap:8px;max-width:1920px;margin:0 auto}
.topbar{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;justify-content:space-between}
.brandline{margin:0;color:var(--muted)}.brandline strong{color:var(--text);font-size:18px}
.live-label{border:1px solid rgba(239,168,58,.5);border-radius:6px;color:var(--warn-text);background:rgba(239,168,58,.08);padding:4px 10px;font-size:13px;font-weight:600}
.mode-switch,.lang{display:inline-flex;gap:2px;padding:2px;border:1px solid var(--line);border-radius:10px;background:var(--surface)}
.mode-switch a,.lang a{display:inline-flex;align-items:center;min-height:32px;padding:4px 11px;color:var(--muted);border-radius:8px;text-decoration:none;font-size:14px;font-weight:550}
.mode-switch a[aria-current="true"],.lang a[aria-current="true"]{background:#151b24;color:var(--text)}
.titlerow{display:flex;gap:16px;align-items:center;justify-content:space-between}
.titlerow h1{margin:0;font-size:30px;letter-spacing:-.01em}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:42px;padding:8px 18px;border:1px solid #efa83a;border-radius:10px;background:#efa83a;color:#241703;font:inherit;font-size:16px;font-weight:700;cursor:pointer}
.btn:disabled{opacity:.6;cursor:default}
.page .surv-ribbon{margin:0;font-size:17px}.page .surv-eval{margin:0;padding:7px 12px;font-size:14px}
.page .surv-grid{flex:1;min-height:0;grid-template-columns:1.32fr 1fr 1fr;grid-template-rows:minmax(0,1fr) minmax(0,1fr);grid-template-areas:"occ ah stock" "occ cash log";gap:12px}
.page .sv-card,.page .sv-card.sv-occupancy,.page .sv-card.sv-after_hours{grid-column:auto;padding:10px 12px;gap:5px;overflow:hidden}
.page .sv-occupancy{grid-area:occ}.page .sv-after_hours{grid-area:ah;grid-column:auto}.page .sv-stock_watch{grid-area:stock}
.page .sv-cash_desk{grid-area:cash}.page .sv-security_log{grid-area:log}
.page .sv-card:not(.sv-occupancy) .w-frame{aspect-ratio:auto;flex:1;min-height:120px}
.page .sv-card:not(.sv-occupancy) .sv-pending{flex:1;display:flex;align-items:center;justify-content:center}
.page .sv-head h3{font-size:17px}.page .sv-metric{font-size:15px}.page .sv-src{font-size:13px}.page .sv-proof{font-size:12px}
.page .sv-how{font-size:12.5px}.page .sv-engine{font-size:12px}
.page .sv-occupancy .sv-rooms li{padding:4px 10px}.page .sv-occupancy .sv-rooms b{font-size:20px}
.page .sv-log{flex:1;min-height:0;font-size:13px;line-height:1.35}
.page .sv-security_log .w-frame{display:none}
.page .sv-occupancy .w-frame{aspect-ratio:auto;flex:1;min-height:300px}
.page .sv-card .sv-big{font-size:19px}
.foot{color:var(--muted);font-size:12px;margin:0}
@media (max-width:1100px){.page{height:auto}.page .surv-grid{grid-template-columns:1fr;grid-template-areas:none;grid-template-rows:none}.page .sv-card{grid-area:auto!important}}
"""


def render_surveillance_page(lang: str = "en") -> str:
    """Vista dedicada ``/?scene=surveillance``: 1920×1080 sin scroll."""
    lang = lang if lang in SV_T else "en"
    t = SV_T[lang]
    labels = dict(t)
    labels["lang_code"] = lang
    data = surveillance_state()
    en_cur = " aria-current='true'" if lang == "en" else ""
    es_cur = " aria-current='true'" if lang == "es" else ""
    script = (
        "const TEXT = " + json.dumps(labels, ensure_ascii=False) + ";\n"
        "const SV = " + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + ";\n"
        "function el(tag, text, cls) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = String(text); return n; }\n"
        "function byId(id) { return document.getElementById(id); }\n"
        "function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }\n"
        + SV_JS
        + "\ndocument.addEventListener('DOMContentLoaded', () => {\n"
        "  renderSurveillance(SV);\n"
        "  (SV.cards || []).forEach((c) => (c.rooms || []).forEach((r) => { if (r.image) { const i = new Image(); i.src = r.image; } }));\n"
        "  const btn = byId('scanBtn'); btn.addEventListener('click', () => scanSite(btn));\n"
        "  if (new URLSearchParams(window.location.search).get('autoscan') === '1') setTimeout(() => scanSite(btn), 600);\n"
        "});\n"
    )
    return (
        "<!doctype html>\n"
        f"<html lang='{_e(lang)}'><head><meta charset='utf-8'>"
        f"<link rel='icon' href=\"{favicon_href()}\">"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_e(BRAND)} — Surveillance · {_e(SUBTITLE)}</title>"
        f"<style>{SV_CSS}{_PAGE_CSS}</style></head><body>"
        "<div class='page'>"
        "<header class='topbar'>"
        f"<p class='brandline'><strong>{brand_mark_html()}</strong> · {_e(SUBTITLE)}</p>"
        f"<span class='live-label'>{_e(t['sv_page_label'])}</span>"
        "<div style='display:flex;gap:8px;flex-wrap:wrap;align-items:center'>"
        f"<nav class='mode-switch scene-switch' aria-label='{_e(t['scene'])}'>"
        f"<a href='/?scene=bodega&lang={lang}'>{_e('Warehouse' if lang == 'en' else 'Bodega')}</a>"
        f"<a href='/?scene=frio&lang={lang}'>{_e('Cold chain' if lang == 'en' else 'Cadena de frío')}</a>"
        f"<a href='/?scene=physical&lang={lang}'>Physical</a>"
        f"<a href='/?scene=sentinel&lang={lang}'>Sentinel</a>"
        f"<a href='/?scene=surveillance&lang={lang}' aria-current='true'>Surveillance</a></nav>"
        f"<span class='lang'><a href='/?scene=surveillance&lang=en'{en_cur}>EN</a>"
        f"<a href='/?scene=surveillance&lang=es'{es_cur}>ES</a></span>"
        "</div></header>"
        "<div class='titlerow'>"
        f"<h1>{_e(t['sv_title'])}</h1>"
        "<div style='display:flex;gap:12px;align-items:center'>"
        f"<span class='hint'>{_e(t['sv_scan_note'])}</span>"
        f"<button class='btn' id='scanBtn' type='button'>{_e(t['sv_scan'])}</button></div></div>"
        "<p class='surv-ribbon' id='svRibbon'></p>"
        "<p class='surv-eval' id='svEval'></p>"
        "<main class='surv-grid' id='svGrid' aria-live='polite'></main>"
        f"<p class='foot'>{_e(t['footer_meta'])}</p>"
        "</div>"
        f"<script>{script}</script></body></html>"
    )
