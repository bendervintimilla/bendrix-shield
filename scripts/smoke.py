"""Prueba de humo de H1: 1 llamada mínima por modelo de la demo.

Uso: ``make smoke`` (en vivo) o ``python scripts/smoke.py --replay``.
Sin créditos (401/402/403) cada llamada se marca ``needs_credits`` y el
script termina en verde (H-COMUN §4). Nunca imprime la llave.
"""

from __future__ import annotations

import base64
import struct
import subprocess
import sys
import wave
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shield.meta_client import MetaClient, NeedsCredits  # noqa: E402

AUDIO_DIR = Path(".smoke-audio")


def tiny_png_data_uri() -> str:
    """PNG sintético de 8x8 (sin archivos externos ni medios pesados)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        raw = tag + data
        return struct.pack(">I", len(data)) + raw + struct.pack(">I", zlib.crc32(raw) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
    rows = b"".join(b"\x00" + b"\xff\x00\x00" * 8 for _ in range(8))
    idat = chunk(b"IDAT", zlib.compress(rows))
    iend = chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(sig + ihdr + idat + iend).decode()


def make_wav() -> Path:
    AUDIO_DIR.mkdir(exist_ok=True)
    wav_path = AUDIO_DIR / "rota-todo.wav"
    # Preferimos la voz real de Paulina; si `say` no está, WAV silencioso válido.
    try:
        subprocess.run(
            [
                "say",
                "-v",
                "Paulina",
                "sí, rota todo",
                "-o",
                str(wav_path),
                "--data-format=LEI16@24000",
            ],
            check=True,
            timeout=30,
            capture_output=True,
        )
        if wav_path.is_file() and wav_path.stat().st_size > 1000:
            return wav_path
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    with wave.open(str(wav_path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(24000)
        fh.writeframes(b"\x00\x00" * 24000)
    return wav_path


def run_step(name: str, fn) -> str:  # noqa: ANN001, ANN202
    try:
        detail = fn()
        print(f"[ok] {name}: {detail}")
        return "ok"
    except NeedsCredits as exc:
        print(f"[needs_credits] {name}: {exc}")
        return "needs_credits"
    except Exception as exc:  # el humo reporta, no esconde
        print(f"[error] {name}: {type(exc).__name__}: {exc}")
        return "error"


def main() -> int:
    replay = "--replay" in sys.argv
    client = MetaClient(replay_only=replay)
    img = tiny_png_data_uri()
    statuses: list[str] = []

    def spark() -> str:
        result = client.chat_completions(
            model="muse-spark-1.3",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Describe the image in one word; call get_weather for Quito.",
                        },
                        {"type": "image_url", "image_url": {"url": img}},
                    ],
                }
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Weather for a city",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    },
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "smoke",
                    "schema": {
                        "type": "object",
                        "properties": {"word": {"type": "string"}},
                        "required": ["word"],
                    },
                },
            },
        )
        return f"costo=${result.cost_usd:.6f} replay={result.from_replay}"

    def wonder() -> str:
        result = client.responses(model="muse-wonder-1.0", input="Reply with: ok")
        return f"costo=${result.cost_usd:.6f} replay={result.from_replay}"

    def voice() -> str:
        result = client.transcribe_file(make_wav())
        text = (result.data.get("transcript") or "")[:60]
        return f"transcript={text!r} costo=${result.cost_usd:.6f}"

    def sam() -> str:
        result = client.sam_segment_image(image_url=img, prompt="red square")
        return f"costo=${result.cost_usd:.6f} replay={result.from_replay}"

    statuses.append(run_step("muse-spark-1.3 (texto+imagen+tools+json_schema)", spark))
    statuses.append(run_step("muse-wonder-1.0 (responses)", wonder))
    statuses.append(run_step("muse-voice-transcribe-1.0 (wav Paulina)", voice))
    statuses.append(run_step("sam-3.1 (imagen sintética)", sam))
    client.close()
    if "error" in statuses:
        print("SMOKE: FAIL (hay errores que no son falta de créditos)")
        return 1
    ok_n = statuses.count("ok")
    nc_n = statuses.count("needs_credits")
    print(f"SMOKE: OK ({ok_n} en vivo/replay, {nc_n} needs_credits)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
