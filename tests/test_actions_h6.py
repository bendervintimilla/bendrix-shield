"""H6 E2E en replay: anomalía en Bodega -> rotación -> atacante 401.

Sin red ni créditos: gateway con MockTransport, registry :memory:.
Compras y Bodega (con su token nuevo vía registro local del SDK) deben
seguir en 200 con 0 errores mientras el token robado pasa a 401.
"""

import time

import httpx
import pytest
from fastapi.testclient import TestClient

from sandbox.attacker import attempt_statuses, format_timeline
from shield.actions import (
    Actions,
    ApprovalRequired,
    ManualStepRequired,
    RotateTokenRunbook,
)
from shield.gateway.app import UPSTREAM_KEY_NAME, create_app
from shield.registry import Registry
from shield.schemas import Decision, PolicyDecision
from shield.sdk.pending import PendingRegistry
from shield.sdk.refresh import ShieldClient
from shield.sdk.token_store import LocalTokenStore
from shield.vault import MemoryVault

UPSTREAM_KEY = "upstream-real-key-0000"
SIXTEEN_HOURS_S = 16 * 3600


def ok_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["authorization"] == f"Bearer {UPSTREAM_KEY}"
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "model": "muse-spark-1.3",
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


def build_gateway(registry):
    app = create_app(
        registry=registry,
        vault=MemoryVault({UPSTREAM_KEY_NAME: UPSTREAM_KEY}),
        upstream_transport=httpx.MockTransport(ok_handler),
        sandbox=True,
    )
    return TestClient(app)


def approve(pending_registry: PendingRegistry, agent="bodega", tool="rotate_token") -> str:
    pending = pending_registry.add(
        agent=agent,
        tool=tool,
        args={},
        decision=PolicyDecision(decision=Decision.ASK_OWNER, reason="simulada", evidence=[]),
    )
    pending_registry.approve(pending.pending_id)
    return pending.pending_id


def post(client, raw, country=None):
    headers = {"Authorization": f"Bearer {raw}"}
    if country:
        headers["X-Demo-Country"] = country
    return client.post(
        "/v1/chat/completions",
        json={"model": "muse-spark-1.3", "messages": [{"role": "user", "content": "cuenta"}]},
        headers=headers,
    )


def test_e2e_replay_rotation_attacker_401_peers_unaffected(tmp_path):
    started = time.perf_counter()
    registry = Registry(":memory:")
    client = build_gateway(registry)
    store = LocalTokenStore(tmp_path / "agent-tokens.json")
    bodega_tok, bodega_raw = registry.create_token("bodega", "crew")
    _, compras_raw = registry.create_token("compras", "crew")
    store.set_token("bodega", bodega_raw, bodega_tok.token_id)
    actions = Actions(registry=registry, token_store=store)

    # Anomalía simulada en replay: el token de Bodega aparece desde un país nuevo.
    assert post(client, bodega_raw, country="EC").status_code == 200
    anomaly = post(client, bodega_raw, country="BR")
    assert anomaly.status_code == 200  # aún válido: la anomalía dispara el plan

    runbook = actions.rotate_token(grace_s=0.3)
    plan = runbook.plan(agent="bodega")
    assert plan.action == "rotate_token" and plan.target == "bodega"
    assert any("gracia" in s for s in plan.steps)

    # Sin aprobación no hay efecto.
    with pytest.raises(ApprovalRequired):
        runbook.apply(plan)

    approval_id = approve(actions.approvals)
    result = runbook.apply(plan, approval_id=approval_id)
    assert result.status == "applied"
    # Idempotente: re-aplicar el mismo plan no crea otro token.
    again = runbook.apply(plan, approval_id=approval_id)
    assert again.new_token_id == result.new_token_id
    assert len(registry.list_tokens("bodega")) == 2

    # Durante la gracia el viejo sigue vivo; Bodega ya usa el nuevo del store.
    assert post(client, bodega_raw).status_code == 200
    assert post(client, store.get_token("bodega")).status_code == 200
    assert post(client, compras_raw).status_code == 200

    time.sleep(0.45)
    verify = runbook.verify(agent="bodega")
    assert verify.ok and verify.details["bodega"] is True

    statuses = attempt_statuses(client, bodega_raw, attempts=2)
    assert statuses == [401, 401]
    assert format_timeline([200, *statuses]) == "200 → 401 → 401"
    # La cuadrilla sigue contando: 0 errores tras la rotación.
    assert post(client, store.get_token("bodega")).status_code == 200
    assert post(client, compras_raw).status_code == 200

    elapsed = time.perf_counter() - started
    assert elapsed < 10
    assert elapsed < SIXTEEN_HOURS_S  # vs ~16 h del incidente real


def test_rotate_without_grace_and_rollback_restores_service(tmp_path):
    registry = Registry(":memory:")
    client = build_gateway(registry)
    store = LocalTokenStore(tmp_path / "t.json")
    tok, raw = registry.create_token("bodega", "crew")
    store.set_token("bodega", raw, tok.token_id)
    actions = Actions(registry=registry, token_store=store)
    runbook = actions.rotate_token(grace_s=0)
    plan = runbook.plan(agent="bodega")
    result = runbook.apply(plan, approval_id=approve(actions.approvals))
    assert post(client, raw).status_code == 401
    assert post(client, store.get_token("bodega")).status_code == 200
    rolled = runbook.rollback(result)
    assert rolled.status == "rolled_back"
    # Tras rollback hay un token activo usable en el store.
    assert post(client, store.get_token("bodega")).status_code == 200


def test_auto_containment_canary_without_approval_is_audited(tmp_path):
    registry = Registry(":memory:")
    store = LocalTokenStore(tmp_path / "t.json")
    tok, raw = registry.create_token("bodega", "crew")
    store.set_token("bodega", raw, tok.token_id)
    actions = Actions(registry=registry, token_store=store, auto_contain=True)
    runbook = actions.revoke()
    plan = runbook.plan(agent="bodega", reason="canary_detected")
    result = runbook.apply(plan)  # sin approval_id: contención automática
    assert result.status == "applied" and result.auto_contained is True
    assert registry.get_token(tok.token_id).status.value == "revoked"
    assert any(e.action == "revoke" and e.auto_contained for e in actions.audit_log)


def test_upstream_key_manual_step_and_sandbox_only(tmp_path):
    vault = MemoryVault({"META_MODEL_API_KEY": "old-key-0000"})
    actions = Actions(registry=Registry(":memory:"), vault=vault, sandbox=False)
    with pytest.raises(PermissionError):
        actions.rotate_upstream_key().plan(provider="meta")
    actions_ok = Actions(registry=Registry(":memory:"), vault=vault, sandbox=True)
    runbook = actions_ok.rotate_upstream_key()
    plan = runbook.plan(provider="meta")
    with pytest.raises(ManualStepRequired):
        runbook.apply(plan, approval_id=approve(actions_ok.approvals, tool="rotate_upstream_key"))
    result = runbook.apply(
        plan,
        approval_id=approve(actions_ok.approvals, tool="rotate_upstream_key"),
        manual_value="new-key-1111",
    )
    assert result.status == "applied"
    assert vault.get("META_MODEL_API_KEY") == "new-key-1111"
    assert "new-key" not in str(result.details)  # nunca el valor, solo huella/last4


def test_sdk_client_recovers_after_rotation_via_local_store(tmp_path):
    store = LocalTokenStore(tmp_path / "t.json")
    store.set_token("bodega", "shd_bodega_old", "tok-old")

    class FakeCompletions:
        def __init__(self, owner):
            self._owner = owner

        def create(self, **kwargs):
            if self._owner.api_key == "shd_bodega_old":
                err = RuntimeError("401 rotated_token")
                err.status_code = 401  # type: ignore[attr-defined]
                raise err
            return {"ok": True, "used": self._owner.api_key}

    class FakeChat:
        def __init__(self, owner):
            self.completions = FakeCompletions(owner)

    class FakeClient:
        def __init__(self):
            self.api_key = "shd_bodega_old"
            self.chat = FakeChat(self)

    raw_client = FakeClient()
    client = ShieldClient(raw_client, store, "bodega")
    # La rotación (actions) escribe el token nuevo en el registro local.
    store.set_token("bodega", "shd_bodega_new", "tok-new")
    out = client.chat.completions.create(model="muse-spark-1.3")
    assert out == {"ok": True, "used": "shd_bodega_new"}
    assert raw_client.api_key == "shd_bodega_new"


def test_rotate_token_runbook_type_export():
    assert RotateTokenRunbook is not None


def test_redeploy_verify_and_patch_plan_sandbox_only():
    registry = Registry(":memory:")
    registry.create_token("bodega", "crew")
    registry.create_token("compras", "crew")
    calls = []
    actions = Actions(
        registry=registry, sandbox=True, deployer=lambda s: calls.append(s) or {"ok": True}
    )
    checked = actions.verify().verify()
    assert checked.ok and checked.details == {"bodega": True, "compras": True}

    redeploy = actions.redeploy()
    plan = redeploy.plan(service="cantina-demo")
    with pytest.raises(Exception):  # sin aprobación no despliega
        redeploy.apply(plan)
    out = redeploy.apply(plan, approval_id=approve(actions.approvals, tool="redeploy"))
    assert out.status == "applied" and calls == ["cantina-demo"]
    assert redeploy.verify(service="cantina-demo").ok
    assert redeploy.rollback(out).status == "rolled_back"

    patch = actions.patch_plan()
    pplan = patch.plan(service="cantina-demo", package="litellm", fixed_version="1.0.1")
    assert any("rollback" in s for s in pplan.steps)
    assert (
        patch.apply(pplan, approval_id=approve(actions.approvals, tool="patch_plan")).status
        == "applied"
    )

    prod = Actions(registry=registry, sandbox=False)
    with pytest.raises(PermissionError):
        prod.redeploy().plan(service="cantina-demo")


def test_wrap_with_token_store_returns_self_healing_client(tmp_path):
    import bendrix_shield

    store = LocalTokenStore(tmp_path / "t.json")

    class FakeCompletions:
        def __init__(self, owner):
            self._owner = owner

        def create(self, **kwargs):
            if self._owner.api_key != "shd_bodega_new":
                err = RuntimeError("401 rotated_token")
                err.status_code = 401  # type: ignore[attr-defined]
                raise err
            return {"ok": True}

    class FakeChat:
        def __init__(self, owner):
            self.completions = FakeCompletions(owner)

    class FakeClient:
        def __init__(self):
            self.api_key = ""
            self.chat = FakeChat(self)

    raw_client = FakeClient()
    client = bendrix_shield.wrap(raw_client, "shd_bodega_old", agent="bodega", token_store=store)
    store.set_token("bodega", "shd_bodega_new", "tok-new")
    assert client.chat.completions.create() == {"ok": True}
    assert raw_client.api_key == "shd_bodega_new"
