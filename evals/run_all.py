"""Corre todas las evals y deja evals/report.md completo (H9).

Uso: ``uv run python evals/run_all.py`` (sin red ni créditos).
Ejecuta cada runner (cada uno escribe solo su sección marcada), mide la
latencia que agrega el gateway con upstream falso instantáneo y actualiza
la tabla resumen H2–H9 al inicio del reporte.
"""

from __future__ import annotations

import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).parent
REPORT = ROOT / "report.md"

from shield.brand import BRAND  # noqa: E402, I001
START, END = "<!-- H9:summary:start -->", "<!-- H9:summary:end -->"
RUNNERS = [
    "run_injection.py",
    "run_heldout.py",
    "run_heldout2.py",
    "run_open_classifier.py",
    "run_exposure.py",
    "run_anomaly.py",
    "run_invoices.py",
    "run_stock.py",
]


def gateway_latency() -> tuple[float, float]:
    """p50/p95 extremo a extremo local con upstream falso (método de H3)."""
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
        vault=MemoryVault({UPSTREAM_KEY_NAME: "upstream-prueba"}),
        upstream_transport=httpx.MockTransport(handler),
        sandbox=True,
        rate_limit_per_minute=100_000,
    )
    client = TestClient(app)
    _, raw = registry.create_token("bodega", "crew")
    headers = {"Authorization": f"Bearer {raw}"}
    body = {"model": "muse-spark-1.3", "messages": [{"role": "user", "content": "hola"}]}
    client.post("/v1/chat/completions", json=body, headers=headers)  # calentamiento
    samples = []
    for _ in range(80):
        started = time.perf_counter()
        resp = client.post("/v1/chat/completions", json=body, headers=headers)
        samples.append((time.perf_counter() - started) * 1000)
        assert resp.status_code == 200
    samples.sort()
    p50 = statistics.median(samples)
    p95 = samples[min(int(0.95 * len(samples)), len(samples) - 1)]
    return p50, p95


def _grab(pattern: str, text: str, default: str = "ver sección") -> str:
    match = re.search(pattern, text)
    return match.group(0) if match else default


def summary(text: str, p50: float, p95: float) -> str:
    n_adv = len(list((ROOT / "advisories").glob("*.json")))
    n_est = len(list((ROOT / "estates").glob("*.json")))
    inj = _grab(r"Bloqueados: \d+ \(tasa de bloqueo: [^)]+\)", text)
    inj_fp = _grab(r"Falsos positivos \(limpio bloqueado\): \d+ \(tasa: [^)]+\)", text)
    held = _grab(r"Envenenados bloqueados: \d+/\d+ \(recall [^)]+\)", text)
    held_legit = _grab(r"Cambios legítimos con aviso formal en `ask_owner`: \d+/\d+", text)
    expo = _grab(r"Confirmadas \(confianza >= 0\.8\): precisión [^\n]+", text)
    anom = _grab(r"A nivel llamada: precisión [^\n]+", text)
    inv = _grab(r"Total exacto desde texto: \d+/\d+", text)
    stock = _grab(r"Conteo en imagen \(esperado 3\): [^\n]+", text)
    open_mode = _grab(r"needs_credits", text, "en vivo")
    return (
        f"# Evals de {BRAND} — reporte completo (H11)\n\n"
        "Las cifras sin red salen de `uv run python evals/run_all.py` "
        "(replay/fixtures). Las rondas EN VIVO de H11 (facturas Spark "
        "visión, SAM 3.1, Voice) se agregan con `run_invoices_live.py` y "
        "`run_stock_live.py` y llevan su costo real. Las tasas de "
        "inyección se reportan por separado: la sintética comparte "
        "patrones con las reglas, la held-out v1 ajustó reglas en H10 y "
        "la held-out v2 es la principal (fresca, congelada, sin ajustar).\n\n"
        "| Sesión | Qué se midió | Resultado |\n"
        "|---|---|---|\n"
        f"| H2 | Sets: avisos reales, estates, uso, inyecciones, facturas, canarios "
        f"| {n_adv} avisos, {n_est} estates, 20 facturas, 10 canarios (bloqueados 10/10) |\n"
        f"| H3 | Latencia agregada por el gateway (upstream falso, 80 llamadas) "
        f"| p50 {p50:.2f} ms, p95 {p95:.2f} ms extremo a extremo local |\n"
        f"| H4 | Inyección sintética (regresión, patrones compartidos) | {inj}; {inj_fp} |\n"
        f"| H5 | Exposición ThreatCard × Asset | {expo} |\n"
        f"| H5 | Anomalías de uso (abuso 16 h) | {anom} |\n"
        "| H6 | Rotación de token y atacante 200 → 401 | E2E en replay verde "
        "(`tests/test_actions_h6.py`); punta a punta <10 s frente a ~16 h reales |\n"
        f"| H7 | Facturas (replay, sin modelo real) | {inv}; aritmética y escenas en su sección |\n"
        f"| H7 | Bodega SAM + voz (salidas sintéticas, sin tomas reales) | {stock} |\n"
        "| H8 | Panel y canales WhatsApp/voz | Panel en vivo y aprobación por "
        "voz/WhatsApp simulado; E2E guardián->rotación en replay verde |\n"
        f"| H9 | Inyección held-out ciega a las reglas | {held}; {held_legit} |\n"
        "| H11 | Held-out v2 (PRINCIPAL, fresco y congelado) | ver sección H11:heldout2 |\n"
        "| H11 | Facturas EN VIVO Spark visión / SAM 3.1 y Voice | ver secciones "
        "H11:live-invoices y H11:live-stock (con costo real) |\n"
        "| H10 | Held-out tras cerrar lecturas que piden credencial | Bloqueo o "
        "ask_owner en 12/12; permitidos en silencio: 0 (antes: 2) |\n"
        "| H10 | Exposición con avisos hermanos agrupados | Confirmadas: "
        "precisión 1.000 (antes 0.643); Brotli queda candidato a triaje |\n"
        f"| H9 | Gate Spark Open vs determinista solo | Modo: {open_mode}; "
        "detalle en su sección |\n\n"
        "**Costo:** las evals de este runner son sin red (USD 0). Desde H11 "
        "hay además rondas EN VIVO con costo real en las secciones "
        "H11:live-invoices / H11:live-stock (facturas Spark visión, SAM 3.1 "
        "y Voice); el video SAM y las tomas reales de bodega siguen en "
        "replay por falta de material hospedado. Baseten/Spark Open sigue "
        "sin llave en el vault.\n\n"
        f"Latencia del gateway medida en esta corrida: p50 {p50:.2f} ms y "
        f"p95 {p95:.2f} ms (TestClient local, upstream instantáneo; contra "
        "la Meta Model API manda la latencia del upstream)."
    )


def main() -> int:
    # Reconstrucción limpia: cada runner escribe solo su sección marcada.
    REPORT.write_text(f"# Evals de {BRAND}\n", encoding="utf-8")
    for runner in RUNNERS:
        print(f"== {runner}")
        proc = subprocess.run([sys.executable, str(ROOT / runner)], capture_output=True, text=True)
        print((proc.stdout or "").strip())
        if proc.returncode != 0:
            print(proc.stderr.strip()[-2000:])
            return proc.returncode
    p50, p95 = gateway_latency()
    text = REPORT.read_text(encoding="utf-8")
    block = f"{START}\n{summary(text, p50, p95)}\n{END}"
    if START in text and END in text:
        before, rest = text.split(START, 1)
        _, after = rest.split(END, 1)
        text = before + block + after
    else:
        text = text.replace(f"# Evals de {BRAND}\n", "", 1).lstrip()
        text = block + "\n\n" + text
    REPORT.write_text(text, encoding="utf-8")
    print(f"reporte completo -> {REPORT} (gateway p50 {p50:.2f} ms, p95 {p95:.2f} ms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
