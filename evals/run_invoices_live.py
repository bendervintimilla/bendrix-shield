"""Eval EN VIVO de facturas — H11: Spark 1.3 visión sobre las 20 sintéticas.

Las 20 facturas de H2 solo traen total/número/moneda en ``raw_text``; el
resto vive en ``ground_truth``. Aquí se renderiza cada factura completa
como imagen (HTML -> PNG con qlmanage, solo macOS) y se extrae con la
ruta real de la cuadrilla (``extract_with_spark_vision``: Muse Spark 1.3
visión + JSON schema). Sin qlmanage o sin créditos se reporta tal cual,
no se simula. Uso: ``uv run python evals/run_invoices_live.py``
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crew.compras.invoice import extract_with_spark_vision, validate_invoice  # noqa: E402
from evals._sections import write_section  # noqa: E402
from shield.meta_client import MetaClient, NeedsCredits  # noqa: E402

INVOICES_DIR = Path(__file__).parent / "invoices"
START, END = "<!-- H11:live-invoices:start -->", "<!-- H11:live-invoices:end -->"
COST_CAP_USD = 3.0


def _norm(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).strip().lower()


def _money_ok(got: float, want: float) -> bool:
    return abs(float(got) - float(want)) <= 0.02


def render_png(truth: dict, out_dir: Path) -> Path:
    name = str(truth["invoice_number"])
    subtotal = float(truth["subtotal"])
    html = (
        '<html><body style="font-family:Helvetica;font-size:28px;padding:40px">'
        f"<h1>FACTURA {name}</h1>"
        f"<p>Proveedor: {truth['vendor']}</p><p>Fecha: {truth['date']}</p>"
        f"<p>Moneda: {truth['currency']}</p>"
        f"<p>1 x Insumos varios @ {subtotal:.2f} = {subtotal:.2f}</p>"
        f"<p>Subtotal: {subtotal:.2f}</p><p>IVA: {float(truth['tax']):.2f}</p>"
        f"<p>Total: {float(truth['total']):.2f}</p></body></html>"
    )
    html_path = out_dir / f"{name}.html"
    html_path.write_text(html, encoding="utf-8")
    subprocess.run(
        ["qlmanage", "-t", "-s", "1400", "-o", str(out_dir), str(html_path)],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return out_dir / f"{name}.html.png"


def main() -> int:
    files = sorted(INVOICES_DIR.glob("invoice-*.json"))
    total_cost = 0.0
    counts = dict.fromkeys(
        ("supplier", "number", "date", "currency", "subtotal", "tax", "total", "valid"), 0
    )
    rows: list[str] = []
    failures: list[str] = []
    status = "ok"
    with tempfile.TemporaryDirectory() as tmp:
        client = MetaClient(replay_dir=Path(tmp) / "replay")
        real_chat = client.chat_completions

        def tracking_chat(**kwargs):  # noqa: ANN202, ANN003
            nonlocal total_cost
            result = real_chat(**kwargs)
            total_cost += float(result.cost_usd)
            return result

        client.chat_completions = tracking_chat  # type: ignore[method-assign]
        try:
            for path in files:
                if total_cost > COST_CAP_USD:
                    status = f"abortada por tope de costo USD {COST_CAP_USD}"
                    break
                data = json.loads(path.read_text(encoding="utf-8"))
                truth = data["ground_truth"]
                png = render_png(truth, Path(tmp))
                uri = "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode()
                inv = extract_with_spark_vision(uri, client=client, doc_id=str(data["invoice_id"]))
                checks = {
                    "supplier": _norm(inv.supplier) == _norm(str(truth["vendor"])),
                    "number": inv.invoice_number == str(truth["invoice_number"]),
                    "date": inv.date == str(truth["date"]),
                    "currency": inv.currency.upper() == str(truth["currency"]).upper(),
                    "subtotal": _money_ok(inv.subtotal, float(truth["subtotal"])),
                    "tax": _money_ok(inv.tax, float(truth["tax"])),
                    "total": _money_ok(inv.total, float(truth["total"])),
                    "valid": validate_invoice(inv).ok,
                }
                for key, ok in checks.items():
                    counts[key] += ok
                bad = [k for k, ok in checks.items() if not ok]
                if bad:
                    failures.append(f"{truth['invoice_number']}: {', '.join(bad)}")
                rows.append(
                    f"| {truth['invoice_number']} | {'ok' if checks['supplier'] else 'FALLA'} "
                    f"| {'ok' if checks['number'] else 'FALLA'} "
                    f"| {'ok' if checks['total'] else 'FALLA'} "
                    f"| {'ok' if checks['valid'] else 'FALLA'} |"
                )
        except NeedsCredits as exc:
            status = f"needs_credits: {exc}"
        finally:
            client.close()
    n = len(files)
    done = len(rows)
    section = (
        "## Eval EN VIVO de facturas (Spark 1.3 visión) — H11\n\n"
        f"Estado: {status}. Facturas procesadas: {done}/{n} (render HTML->PNG "
        "en macOS + `extract_with_spark_vision`, misma ruta de la cuadrilla). "
        "El documento renderizado trae una línea `1 x Insumos varios` por el "
        "subtotal: mide extracción de campos y aritmética, no OCR de un "
        "escaneo real de proveedor.\n\n"
        f"- Proveedor exacto (sin acentos/mayúsculas): {counts['supplier']}/{done or n}\n"
        f"- Número: {counts['number']}/{done or n} · Fecha: {counts['date']}/{done or n} "
        f"· Moneda: {counts['currency']}/{done or n}\n"
        f"- Subtotal: {counts['subtotal']}/{done or n} · IVA: {counts['tax']}/{done or n} "
        f"· Total: {counts['total']}/{done or n} (tol. 0,02)\n"
        f"- Validación aritmética de la extracción: {counts['valid']}/{done or n}\n"
        f"- Costo real de esta corrida: USD {total_cost:.4f}\n"
        + (
            f"- Fallas por campo: {'; '.join(failures)}\n"
            if failures
            else "- Sin fallas por campo.\n"
        )
        + "\n| factura | proveedor | número | total | aritmética |\n|---|---|---|---|---|\n"
        + "\n".join(rows)
        + "\n"
    )
    write_section(START, END, section)
    print(f"facturas en vivo: {done}/{n} costo=USD {total_cost:.4f} estado={status}")
    print(f"totales: {counts['total']}/{done or n}, validación {counts['valid']}/{done or n}")
    return 0 if status == "ok" and done == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
