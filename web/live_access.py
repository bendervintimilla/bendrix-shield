"""Modo en vivo publicado: código de acceso + tope de gasto duro en el servidor.

Solo se activa con ``SHIELD_LIVE_REMOTE=1`` y ``LIVE_ACCESS_CODE`` (de Secret
Manager, ``--set-secrets``). Sin eso, ``/live`` sigue siendo solo loopback
(``make live``) y la demo pública en replay no cambia.

* ``AccessGate``: cookie firmada (HMAC con el propio código) de 12 h, HttpOnly,
  Secure y SameSite=Strict; bloqueo temporal tras fallos de inicio de sesión.
* ``SpendLedger``: tope por día (Ecuador): USD 5 y 20 corridas por defecto. Si
  se alcanza, el servidor responde 429 con un mensaje claro y NO llama al
  modelo. El registro se guarda en un objeto de GCS (sobrevive reinicios) y
  falla cerrado si no se puede leer. Cada actualización deja una línea JSON
  en el log con el costo de la corrida.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from urllib.parse import quote

COOKIE_NAME = "live_auth"
COOKIE_TTL_S = 12 * 3600
TICKET_TTL_S = 600
FAIL_LIMIT = 5
LOCK_S = 300
MIN_CODE_LEN = 16
# Reserva antes de cada paso: lo máximo que un paso suele costar. Evita pasarse
# del tope por una llamada en curso.
STEP_RESERVE_USD = 0.10
ECUADOR = timezone(timedelta(hours=-5))


def remote_enabled() -> bool:
    code = os.environ.get("LIVE_ACCESS_CODE", "")
    return os.environ.get("SHIELD_LIVE_REMOTE", "") == "1" and len(code) >= MIN_CODE_LEN


def _mac(code: str, label: str, exp: int) -> str:
    return hmac.new(code.encode(), f"{label}|{exp}".encode(), hashlib.sha256).hexdigest()


def make_ticket(code: str, ttl_s: int = TICKET_TTL_S, now: float | None = None) -> str:
    """Enlace de un solo uso corto para pruebas automáticas (no revela el código)."""
    exp = int((now if now is not None else time.time()) + ttl_s)
    return f"{exp}.{_mac(code, 'ticket', exp)}"


class AccessGate:
    def __init__(self, code: str) -> None:
        self._code = code
        self._fails: list[float] = []
        self._locked_until = 0.0
        self._lock = threading.Lock()

    def locked_for(self, now: float | None = None) -> int:
        now = now if now is not None else time.time()
        return max(0, int(self._locked_until - now))

    def check_code(self, candidate: str, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        with self._lock:
            if now < self._locked_until:
                return False
            ok = hmac.compare_digest(candidate.encode(), self._code.encode())
            if ok:
                self._fails.clear()
                return True
            self._fails = [t for t in self._fails if now - t < LOCK_S] + [now]
            if len(self._fails) >= FAIL_LIMIT:
                self._locked_until = now + LOCK_S
                self._fails.clear()
            return False

    def _verify(self, value: str, label: str, now: float) -> bool:
        try:
            exp_s, mac = value.split(".", 1)
            exp = int(exp_s)
        except ValueError:
            return False
        if exp < now:
            return False
        return hmac.compare_digest(mac, _mac(self._code, label, exp))

    def make_cookie(self, now: float | None = None) -> str:
        exp = int((now if now is not None else time.time()) + COOKIE_TTL_S)
        return f"{exp}.{_mac(self._code, 'cookie', exp)}"

    def cookie_ok(self, value: str | None, now: float | None = None) -> bool:
        if not value:
            return False
        return self._verify(value, "cookie", now if now is not None else time.time())

    def ticket_ok(self, value: str | None, now: float | None = None) -> bool:
        if not value:
            return False
        return self._verify(value, "ticket", now if now is not None else time.time())


# -- registro de gasto -------------------------------------------------------


class LedgerStore(Protocol):
    def load(self) -> dict[str, Any] | None: ...
    def save(self, data: dict[str, Any]) -> None: ...


class MemoryStore:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data = data

    def load(self) -> dict[str, Any] | None:
        return self.data

    def save(self, data: dict[str, Any]) -> None:
        self.data = json.loads(json.dumps(data))


class GcsStore:
    """Un objeto JSON en GCS leído y escrito con el token del servicio (metadata)."""

    def __init__(self, uri: str) -> None:
        if not uri.startswith("gs://") or "/" not in uri[5:]:
            raise ValueError("SHIELD_LEDGER_GCS must look like gs://bucket/object.json")
        self.bucket, self.name = uri[5:].split("/", 1)

    def _token(self) -> str:
        import httpx

        resp = httpx.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"},
            timeout=5.0,
        )
        resp.raise_for_status()
        return str(resp.json()["access_token"])

    def load(self) -> dict[str, Any] | None:
        import httpx

        url = (
            f"https://storage.googleapis.com/storage/v1/b/{self.bucket}/o/"
            f"{quote(self.name, safe='')}?alt=media"
        )
        resp = httpx.get(url, headers={"Authorization": f"Bearer {self._token()}"}, timeout=10.0)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return dict(resp.json())

    def save(self, data: dict[str, Any]) -> None:
        import httpx

        url = (
            f"https://storage.googleapis.com/upload/storage/v1/b/{self.bucket}/o"
            f"?uploadType=media&name={quote(self.name, safe='')}"
        )
        resp = httpx.post(
            url,
            content=json.dumps(data).encode(),
            headers={
                "Authorization": f"Bearer {self._token()}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        resp.raise_for_status()


def _today() -> str:
    return datetime.now(ECUADOR).strftime("%Y-%m-%d")


class SpendLedger:
    def __init__(
        self,
        store: LedgerStore | None = None,
        *,
        max_usd: float | None = None,
        max_runs: int | None = None,
        today=_today,
    ) -> None:
        self.max_usd = (
            max_usd if max_usd is not None else float(os.environ.get("SHIELD_LIVE_DAILY_USD", "5"))
        )
        self.max_runs = (
            max_runs
            if max_runs is not None
            else int(os.environ.get("SHIELD_LIVE_DAILY_RUNS", "20"))
        )
        self._store = store if store is not None else MemoryStore()
        self._today = today
        self._lock = threading.Lock()
        self._data: dict[str, Any] | None = None
        self._load_error = ""

    @classmethod
    def from_env(cls) -> SpendLedger:
        uri = os.environ.get("SHIELD_LEDGER_GCS", "")
        return cls(GcsStore(uri) if uri else MemoryStore())

    # -- internos (con el candado tomado) --
    def _ensure(self) -> bool:
        day = self._today()
        if self._data is None:
            try:
                loaded = self._store.load()
            except Exception as exc:  # falla cerrado: sin registro no se gasta
                self._load_error = f"ledger unreadable: {type(exc).__name__}"
                return False
            self._load_error = ""
            self._data = loaded or {"day": day, "runs": {}}
        if self._data.get("day") != day:
            self._data = {"day": day, "runs": {}}
        return True

    def _spent(self) -> float:
        return round(sum(float(r.get("cost_usd") or 0) for r in self._data["runs"].values()), 6)

    def _persist(self) -> None:
        try:
            self._store.save(self._data)
        except Exception as exc:
            self._load_error = f"ledger not saved: {type(exc).__name__}"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            ok = self._ensure()
            data = self._data if ok else {"day": self._today(), "runs": {}}
            spent = round(sum(float(r.get("cost_usd") or 0) for r in data["runs"].values()), 6)
            return {
                "day": data["day"],
                "tz": "America/Guayaquil",
                "runs": len(data["runs"]),
                "max_runs": self.max_runs,
                "spent_usd": spent,
                "max_usd": self.max_usd,
                "ledger_ok": ok,
                "ledger_error": self._load_error,
                "per_run": {
                    rid: {"cost_usd": r.get("cost_usd"), "steps": r.get("steps")}
                    for rid, r in data["runs"].items()
                },
            }

    def allow(self, run_id: str) -> tuple[bool, str]:
        """¿Se puede dar un paso que llama al modelo? Si no, el mensaje claro."""
        with self._lock:
            if not self._ensure():
                return False, (
                    "Spend ledger unavailable, so live mode is paused (no model was called)."
                )
            runs = self._data["runs"]
            if run_id not in runs and len(runs) >= self.max_runs:
                return False, (
                    f"Daily limit reached: {self.max_runs} live runs today. "
                    "No model was called. Try again tomorrow (Ecuador time)."
                )
            if self._spent() + STEP_RESERVE_USD > self.max_usd:
                return False, (
                    f"Daily spend limit reached (USD {self.max_usd:.2f}). "
                    "No model was called. Try again tomorrow (Ecuador time)."
                )
            return True, ""

    def record(self, run_id: str, run_total_usd: float, step: str) -> dict[str, Any]:
        """Anota el costo acumulado de la corrida (valor absoluto) tras un paso."""
        with self._lock:
            if not self._ensure():
                return {}
            run = self._data["runs"].setdefault(
                run_id, {"cost_usd": 0.0, "steps": 0, "started": time.time()}
            )
            run["cost_usd"] = round(float(run_total_usd or 0), 6)
            run["steps"] = int(run.get("steps") or 0) + 1
            self._persist()
            line = {
                "event": "live_run_cost",
                "day": self._data["day"],
                "run_id": run_id,
                "step": step,
                "run_cost_usd": run["cost_usd"],
                "day_spent_usd": self._spent(),
                "day_runs": len(self._data["runs"]),
            }
            print(json.dumps(line), flush=True)
            return line


# -- páginas -------------------------------------------------------------------

LOGIN_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NoKey · live mode</title>
<style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b1117;
color:#e6edf3;font:16px system-ui,sans-serif}}
main{{width:min(420px,calc(100vw - 32px))}}
h1{{font-size:22px;margin:0 0 6px}} p{{color:#9fb0c0;line-height:1.45}}
input,button{{font:inherit;width:100%;box-sizing:border-box;padding:12px;border-radius:8px;
border:1px solid #2b3a48;background:#121b24;color:inherit;margin-top:10px}}
button{{background:#1f6f4a;border-color:#2e8b5f;cursor:pointer}}
.err{{color:#ff9d9d}}
</style></head><body><main>
<h1>NoKey · live mode</h1>
<p>Real Meta models (Muse Spark, SAM 3.1, Voice Transcribe). Access code required;
spend is capped on the server (USD {usd} and {runs} runs per day).</p>
{message}
<form method="post" action="/live/login">
<input type="password" name="code" placeholder="Access code" autocomplete="current-password"
autofocus required>
<button type="submit">Enter</button>
</form>
<p><a href="/" style="color:#7fc8a9">Public replay demo (no spend)</a></p>
</main></body></html>"""


def render_login(usd: float, runs: int, message: str = "") -> str:
    msg = f'<p class="err">{message}</p>' if message else ""
    return LOGIN_HTML.format(usd=f"{usd:.0f}", runs=runs, message=msg)
