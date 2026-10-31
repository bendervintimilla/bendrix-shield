# Spark Open classifier

Code: `shield/gate/open_classifier.py`. Tests with doubles (no network):
`tests/test_open_classifier_h9.py`.

## Live status: NOT RUN LIVE

**This classifier has not been run live.** No live run was made while
hardening it, no API key was used, and no live results are claimed in
this document. Anything about live behaviour remains unverified until
someone runs it with credits (see "How to run it" below).

Spark Open has not been run live for lack of credits. The hardening
below is covered only by tests with doubles.

## What the code does

- Model slug (source: `MODEL` in `shield/gate/open_classifier.py`):
  `meta-models/muse-spark-open-1026`, changeable with
  `SHIELD_SPARK_OPEN_MODEL`.
- Primary provider: Baseten Model APIs, an OpenAI-compatible
  `POST https://inference.baseten.co/v1/chat/completions` endpoint
  (source: `BASETEN_BASE_URL` in the same file). Fallback: a Modal
  endpoint with the same Chat Completions shape, configured by the
  operator in `SHIELD_SPARK_OPEN_MODAL_URL`.
- Provider selection: `SHIELD_SPARK_OPEN_PROVIDER=baseten|modal`
  (default `baseten`); `SHIELD_SPARK_OPEN_FALLBACK=modal` tries Modal
  when Baseten reports no credits and Modal is configured.
- API key: vault entry `baseten-api-key` (or `modal-api-key`), or the
  `BASETEN_API_KEY` / `MODAL_API_KEY` environment variables for CI.
  The key value is never logged.
- The request asks for a JSON schema with `label` in
  `clean|secret|injection`, `score`, and `reason`. Per
  `shield/gate/check.py`, the gate blocks only on `secret` or
  `injection` with score >= 0.8.
- Token headroom: the request sends `max_tokens`, default `4096`
  (source: `DEFAULT_MAX_TOKENS`), configurable with
  `SHIELD_SPARK_OPEN_MAX_TOKENS`. An invalid or non-positive value
  falls back to the default. The constructor argument `max_tokens`
  takes precedence over the environment.
- Empty or truncated responses: an empty `message.content`, or any
  response with `finish_reason='length'`, is a failure — never
  `clean`, even if truncated content happens to parse as a `clean`
  verdict. The classifier retries exactly once with twice the token
  headroom. If the retry also fails that way, it returns
  `unclassified` with a reason marked `truncated_or_empty`, which
  does not block on its own: the deterministic layer (regex redaction
  and canaries in the gate) remains in charge, as it does on
  `needs_credits`.
- Without a key, or on HTTP 401/402/403, the classifier returns
  `needs_credits` and does not block. With `SHIELD_REPLAY=1` it
  answers only from the hash cache in `SHIELD_REPLAY_DIR`; a miss is
  also `needs_credits`, and a cached truncated/empty response is
  returned as the marked `unclassified` failure above.

## How to run it (when credits exist)

Do not run the live steps until a Baseten key and credits actually
exist. No step below was executed for this hardening.

1. Put the key in the vault as `baseten-api-key`, or set
   `BASETEN_API_KEY` in the environment (CI). Optionally set
   `SHIELD_SPARK_OPEN_MAX_TOKENS` to change the token headroom.
2. Offline check first (doubles only, no network, no key):

   ```bash
   uv run pytest tests/test_open_classifier_h9.py -q
   ```

3. Live evaluation (this makes real model calls and rewrites the
   H9 section of `evals/report.md`; source:
   `evals/run_open_classifier.py`):

   ```bash
   uv run python evals/run_open_classifier.py
   ```

   Without a key it reports `needs_credits` mode and the combined
   arm matches the deterministic-only arm.
4. To activate the classifier in code once a live run is wanted:

   ```python
   from shield.gate import make_open_classifier, set_classifier

   set_classifier(make_open_classifier())  # Baseten by default
   ```

   For Modal instead, set `SHIELD_SPARK_OPEN_PROVIDER=modal` (or
   `SHIELD_SPARK_OPEN_FALLBACK=modal`) and
   `SHIELD_SPARK_OPEN_MODAL_URL=https://<your-endpoint>/v1`, with the
   key in the vault as `modal-api-key` or in `MODAL_API_KEY`.
