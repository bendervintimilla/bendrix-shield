"""Eval EN VIVO de bodega — H11: SAM 3.1 y Voice reales, sin tomas reales.

No hay tomas de bodega del local (siguen en ``evals/private/tomas.md``,
grabación de H11-B). Lo que sí se repite con el modelo real aquí:

- SAM 3.1 sobre imágenes sintéticas generadas en el acto (rectángulos
  rojos sobre blanco, conteos esperados 3/5/2/0) vía ``count_stock`` de
  la cuadrilla. Mide el conteo del modelo, no una bodega real.
- Voice: dictado generado con ``say`` (voz Paulina, macOS) y transcrito
  con Muse Voice real; el parseo a ítems es el determinista de la cuadrilla.
- Video SAM queda en replay: SAM pide URL/file_id y no hay video
  hospedado del sandbox; no se inventa una cifra en vivo.

Uso: ``uv run python evals/run_stock_live.py``
"""

from __future__ import annotations

import base64
import struct
import subprocess
import sys
import tempfile
import wave
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crew.bodega.agent import BodegaAgent  # noqa: E402
from crew.compras.ledger import Ledger  # noqa: E402
from evals._sections import write_section  # noqa: E402
from shield.meta_client import MetaClient, NeedsCredits  # noqa: E402
from shield.sdk.pending import PendingRegistry  # noqa: E402

START, END = "<!-- H11:live-stock:start -->", "<!-- H11:live-stock:end -->"


def png_with_boxes(count: int) -> bytes:
    """PNG RGB 640x480 blanco con ``count`` rectángulos rojos (stdlib)."""
    width, height = 640, 480
    rows = bytearray()
    boxes = [(40 + i * 115, 180, 130 + i * 115, 320) for i in range(count)]
    for y in range(height):
        rows.append(0)
        for x in range(width):
            red = any(x0 <= x < x1 and y0 <= y < y1 for x0, y0, x1, y1 in boxes)
            rows += b"\xff\x00\x00" if red else b"\xff\xff\xff"

    def chunk(tag: bytes, data: bytes) -> bytes:
        raw = tag + data
        return struct.pack(">I", len(data)) + raw + struct.pack(">I", zlib.crc32(raw) & 0xFFFFFFFF)

    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(bytes(rows)))
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + chunk(b"IEND", b"")


def make_dictation_wav(path: Path) -> bool:
    try:
        subprocess.run(
            [
                "say",
                "-v",
                "Paulina",
                "doce huevos, tres litros de leche",
                "-o",
                str(path),
                "--data-format=LEI16@24000",
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return path.is_file() and path.stat().st_size > 1000
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def main() -> int:
    total_cost = 0.0
    sam_rows: list[str] = []
    sam_ok = 0
    voice_line = "Voz en vivo: no corrida."
    status = "ok"
    with tempfile.TemporaryDirectory() as tmp:
        client = MetaClient(replay_dir=Path(tmp) / "replay")
        bodega = BodegaAgent(Ledger(), meta_client=client, registry=PendingRegistry())
        try:
            for expected in (3, 5, 2, 0):
                uri = "data:image/png;base64," + base64.b64encode(png_with_boxes(expected)).decode()
                out = bodega.count_stock({"kind": "image", "url": uri}, ["red rectangle"])
                got = int(out["counts"][0]["count"])
                total_cost += float(out["cost_usd"])
                sam_ok += got == expected
                sam_rows.append(f"| {expected} | {got} | {'ok' if got == expected else 'FALLA'} |")
            wav = Path(tmp) / "dictado.wav"
            if make_dictation_wav(wav):
                heard = bodega.transcribe(wav)
                items = {i["item"]: i["qty"] for i in heard["items"]}
                ok = items.get("huevos") == 12.0 and items.get("leche") == 3.0
                voice_line = (
                    f"Voz en vivo (say Paulina -> Voice): transcripción "
                    f"{heard['transcript']!r} -> {items} ({'ok' if ok else 'FALLA'})."
                )
            else:
                # WAV silencioso válido: la llamada igual es real, el parseo no.
                with wave.open(str(wav), "wb") as fh:
                    fh.setnchannels(1)
                    fh.setsampwidth(2)
                    fh.setframerate(24000)
                    fh.writeframes(b"\x00\x00" * 24000)
                heard = bodega.transcribe(wav)
                voice_line = (
                    "Voz en vivo: sin `say` en esta máquina; se transcribió un "
                    f"WAV silencioso (transcripción {heard['transcript']!r}), "
                    "el dictado a ítems queda solo en replay."
                )
        except NeedsCredits as exc:
            status = f"needs_credits: {exc}"
        finally:
            client.close()
    section = (
        "## Eval EN VIVO de bodega (SAM 3.1 + Voice) — H11\n\n"
        f"Estado: {status}. **Sin tomas reales de bodega**: imágenes "
        "sintéticas con conteo conocido; el video SAM sigue en replay "
        "(sin video hospedado del sandbox). No es una cifra de bodega real.\n\n"
        f"- SAM 3.1 imagen (prompt `red rectangle`): {sam_ok}/4 conteos exactos. "
        "Nota de transparencia: con el prompt `red box` sobre estas mismas "
        "imágenes SAM devolvió 0 en los casos con rectángulos (solo acertó "
        "el vacío, 1/4); el descriptor exacto de la forma importa y se "
        "reportan los dos.\n"
        f"- {voice_line}\n"
        f"- Costo real de esta corrida: USD {total_cost:.4f} "
        "(SAM por imagen según pricing oficial; Voice casi cero en WAV corto).\n\n"
        "| esperado | contado | resultado |\n|---|---|---|\n" + "\n".join(sam_rows) + "\n"
    )
    write_section(START, END, section)
    print(f"stock en vivo: SAM {sam_ok}/4 costo=USD {total_cost:.4f} estado={status}")
    print(voice_line)
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
