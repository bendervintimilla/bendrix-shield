"""Cliente de Shield sobre la Meta Model API (compatible con OpenAI).

Rutas y campos verificados en la doc oficial el 28-oct-2026 (ver docs/MODELS.md):

- Base: ``https://api.meta.ai/v1``
- ``POST /v1/chat/completions`` — Muse Spark (``muse-spark-1.3``), OpenAI-compatible.
- ``POST /v1/responses`` — Responses API (Spark/Wonder y SAM 3.1).
- ``POST /v1/asr/transcribe`` — Muse Voice Transcribe (multipart: ``request`` JSON + ``audio`` WAV).
- SAM 3.1 va por ``POST /v1/responses`` con ``model="sam-3.1"`` e ``input_image``.

Todo payload saliente pasa por ``gate.check`` antes de salir (SPEC §2.4).
Ante ``429`` reintenta con backoff exponencial + jitter y respeta ``Retry-After``.
Sin créditos (401/402/403) levanta :class:`NeedsCredits` para que el humo y la
demo sigan en modo replay sin fallar.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from shield.gate.check import GateBlocked
from shield.gate.check import check as gate_check

BASE_URL = "https://api.meta.ai/v1"
DEFAULT_TIMEOUT_S = 120.0

# Precios Standard (USD) leídos de https://dev.meta.ai/docs/pricing-rate-limits
# el 28-oct-2026. Por 1M de tokens salvo que se indique otra unidad.
TOKEN_PRICES_PER_1M: dict[str, dict[str, float]] = {
    "muse-wonder-1.0": {"cached_input": 0.20, "input": 4.00, "output": 20.00},
    "muse-spark-1.3": {"cached_input": 0.15, "input": 1.25, "output": 4.25},
    "muse-spark-1.2": {"cached_input": 0.15, "input": 1.25, "output": 4.25},
    "muse-spark-1.1": {"cached_input": 0.15, "input": 1.25, "output": 4.25},
    "muse-spark-1.3-contributor": {"cached_input": 0.002, "input": 0.10, "output": 0.20},
    "muse-spark-1.2-contributor": {"cached_input": 0.002, "input": 0.10, "output": 0.20},
}
VOICE_USD_PER_HOUR = 0.18
SAM_USD_PER_IMAGE = 2.50 / 1000
SAM_USD_PER_1000_FRAMES = 0.20
IMAGE_USD_PER_IMAGE = 0.01


class NeedsCredits(RuntimeError):
    """La API respondió 401/402/403: sin llave válida o sin créditos/tarjeta."""

    def __init__(self, status_code: int, detail: str = "") -> None:
        super().__init__(f"needs_credits (HTTP {status_code}) {detail}".strip())
        self.status_code = status_code


class MetaAPIError(RuntimeError):
    def __init__(self, status_code: int, detail: str = "") -> None:
        super().__init__(f"Meta Model API HTTP {status_code}: {detail}".strip())
        self.status_code = status_code


@dataclass
class CallResult:
    data: dict[str, Any]
    model: str
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    from_cache: bool = False
    from_replay: bool = False
    replay_hash: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    upstream_request_id: str | None = None


def get_api_key() -> str | None:
    """Llave sin imprimirla nunca: env → llavero de macOS (solo lectura)."""
    for var in ("META_MODEL_API_KEY", "MODEL_API_KEY"):
        value = os.environ.get(var)
        if value:
            return value
    try:
        out = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                "meta-model-api-key",
                "-a",
                "hackathon",
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def compute_cost_usd(model: str, usage: dict[str, Any] | None) -> float:
    """Costo de una llamada según la tabla de precios de la doc."""
    usage = usage or {}
    if model == "sam-3.1":
        frames = usage.get("video_frames_processed")
        if frames:
            return (float(frames) / 1000) * SAM_USD_PER_1000_FRAMES
        return SAM_USD_PER_IMAGE
    if model == "muse-image-1.0":
        return IMAGE_USD_PER_IMAGE
    if not usage:
        return 0.0
    if model == "muse-voice-transcribe-1.0":
        ms = float(usage.get("audioDurationMs") or usage.get("audio_duration_ms") or 0)
        if ms <= 0:
            return 0.0
        return (ms / 3_600_000) * VOICE_USD_PER_HOUR
    prices = TOKEN_PRICES_PER_1M.get(model)
    if not prices:
        return 0.0
    input_tokens = float(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    output_tokens = float(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    details = usage.get("input_tokens_details") or {}
    cached = float(details.get("cached_tokens") or usage.get("cached_tokens") or 0)
    fresh = max(input_tokens - cached, 0.0)
    return (
        fresh * prices["input"] + cached * prices["cached_input"] + output_tokens * prices["output"]
    ) / 1_000_000


def payload_hash(path: str, payload: object) -> str:
    canonical = json.dumps({"path": path, "payload": payload}, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class MetaClient:
    """Cliente HTTP mínimo y testeable sobre la Meta Model API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = BASE_URL,
        replay_dir: str | Path | None = None,
        replay_only: bool = False,
        max_retries: int = 4,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: httpx.BaseTransport | None = None,
        gate_fn: Callable[[object], Any] = gate_check,
        sleep_fn: Callable[[float], None] = time.sleep,
        fresh: bool = False,
    ) -> None:
        self._api_key = api_key if api_key is not None else get_api_key()
        self.base_url = base_url.rstrip("/")
        self.replay_dir = (
            Path(replay_dir)
            if replay_dir
            else Path(os.environ.get("SHIELD_REPLAY_DIR", "replay-cache"))
        )
        self.replay_only = replay_only or os.environ.get("SHIELD_REPLAY") == "1"
        self.max_retries = max_retries
        self.fresh = fresh
        self._gate_fn = gate_fn
        self._sleep = sleep_fn
        self._cache: dict[str, CallResult] = {}
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout_s, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> MetaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- internos ---------------------------------------------------------

    def _gate(self, payload: object) -> None:
        result = self._gate_fn(payload)
        allowed = getattr(result, "allowed", True)
        if not allowed:
            raise GateBlocked(f"gate blocked payload: {result}")

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise NeedsCredits(401, "META_MODEL_API_KEY no configurada")
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    def _replay_path(self, digest: str) -> Path:
        return self.replay_dir / f"{digest}.json"

    def _load_replay(self, digest: str) -> dict[str, Any] | None:
        path = self._replay_path(digest)
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def _save_replay(self, digest: str, data: dict[str, Any]) -> None:
        self.replay_dir.mkdir(parents=True, exist_ok=True)
        self._replay_path(digest).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _retry_delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return max(float(retry_after), 0.0)
            except ValueError:
                pass
        return (0.5 * (2**attempt)) + random.uniform(0, 0.25)

    @staticmethod
    def _upstream_id(resp: httpx.Response) -> str | None:
        return (
            resp.headers.get("x-request-id")
            or resp.headers.get("request-id")
            or resp.headers.get("x-upstream-request-id")
            or None
        )

    def _post_json(self, path: str, payload: dict[str, Any], *, model: str) -> CallResult:
        self._gate(payload)
        digest = payload_hash(path, payload)
        if not self.fresh and digest in self._cache:
            hit = self._cache[digest]
            return CallResult(
                data=hit.data,
                model=model,
                cost_usd=0.0,
                from_cache=True,
                replay_hash=digest,
                usage=hit.usage,
                upstream_request_id=hit.upstream_request_id,
            )
        replayed = None if self.fresh else self._load_replay(digest)
        if replayed is not None:
            usage = replayed.get("usage") or {}
            result = CallResult(
                data=replayed,
                model=model,
                cost_usd=compute_cost_usd(model, usage),
                from_replay=True,
                replay_hash=digest,
                usage=usage,
            )
            self._cache[digest] = result
            return result
        if self.replay_only:
            raise NeedsCredits(0, f"replay miss para {path} (hash {digest[:12]}…)")
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.post(path, json=payload, headers=self._headers())
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    self._sleep(self._retry_delay(attempt, None))
                    continue
                raise MetaAPIError(0, str(exc)) from exc
            if resp.status_code == 429 and attempt < self.max_retries:
                self._sleep(self._retry_delay(attempt, resp.headers.get("Retry-After")))
                continue
            if resp.status_code in (401, 402, 403):
                raise NeedsCredits(resp.status_code, resp.text[:200])
            if resp.status_code >= 400:
                raise MetaAPIError(resp.status_code, resp.text[:500])
            data = resp.json()
            latency = (time.perf_counter() - started) * 1000
            usage = data.get("usage") or {}
            result = CallResult(
                data=data,
                model=model,
                cost_usd=compute_cost_usd(model, usage),
                latency_ms=latency,
                replay_hash=digest,
                usage=usage,
                upstream_request_id=self._upstream_id(resp),
            )
            if not self.fresh:
                self._cache[digest] = result
                self._save_replay(digest, data)
            return result
        raise MetaAPIError(429, f"reintentos agotados: {last_error}")

    # -- API pública ------------------------------------------------------

    def chat_completions(
        self, *, model: str, messages: list[dict[str, Any]], **kwargs: Any
    ) -> CallResult:
        payload: dict[str, Any] = {"model": model, "messages": messages, **kwargs}
        return self._post_json("/chat/completions", payload, model=model)

    def responses(self, *, model: str, input: Any, **kwargs: Any) -> CallResult:  # noqa: A002
        payload: dict[str, Any] = {"model": model, "input": input, **kwargs}
        return self._post_json("/responses", payload, model=model)

    def sam_segment_image(self, *, image_url: str, prompt: str) -> CallResult:
        """SAM 3.1 sobre una imagen, vía Responses API (doc SAM overview)."""
        return self.responses(
            model="sam-3.1",
            input=[
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": image_url},
                    ],
                }
            ],
        )

    def transcribe_file(
        self,
        wav_path: str | Path,
        *,
        model: str = "muse-voice-transcribe-1.0",
        fresh: bool | None = None,
    ) -> CallResult:
        """Transcribe un WAV: ``POST /v1/asr/transcribe`` multipart (doc speech-to-text)."""
        path = Path(wav_path)
        request_obj: dict[str, Any] = {
            "mode": "PUSH_TO_TALK",
            "model": model,
            "audioEncoding": "WAV",
        }
        self._gate(request_obj)
        use_fresh = self.fresh if fresh is None else fresh
        digest = payload_hash("/asr/transcribe", {"request": request_obj, "file": path.name})
        replayed = None if use_fresh else self._load_replay(digest)
        if replayed is not None:
            return CallResult(
                data=replayed,
                model=model,
                cost_usd=compute_cost_usd(model, replayed),
                from_replay=True,
                replay_hash=digest,
            )
        if self.replay_only:
            raise NeedsCredits(0, "replay miss para /asr/transcribe")
        if not self._api_key:
            raise NeedsCredits(401, "META_MODEL_API_KEY no configurada")
        started = time.perf_counter()
        with path.open("rb") as fh:
            files = {
                "request": (None, json.dumps(request_obj), "application/json"),
                "audio": (path.name, fh, "audio/wav"),
            }
            resp = self._client.post(
                "/asr/transcribe",
                files=files,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        if resp.status_code in (401, 402, 403):
            raise NeedsCredits(resp.status_code, resp.text[:200])
        if resp.status_code >= 400:
            raise MetaAPIError(resp.status_code, resp.text[:500])
        data = resp.json()
        if not use_fresh:
            self._save_replay(digest, data)
        return CallResult(
            data=data,
            model=model,
            cost_usd=compute_cost_usd(model, data),
            latency_ms=(time.perf_counter() - started) * 1000,
            replay_hash=digest,
            upstream_request_id=self._upstream_id(resp),
        )

    def openai_client(self) -> Any:
        """Cliente OpenAI apuntado a Meta, para código que ya usa ese SDK."""
        from openai import OpenAI

        if not self._api_key:
            raise NeedsCredits(401, "META_MODEL_API_KEY no configurada")
        return OpenAI(base_url=self.base_url, api_key=self._api_key)
