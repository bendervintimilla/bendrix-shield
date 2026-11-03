"""C2491: aprobaciones de un solo uso, ligadas a acción + token, con nonce y caducidad."""

from __future__ import annotations

import time

import pytest

from channels.approvals import ApprovalBroker, ApprovalRejected
from channels.voice import VoiceApprovalFlow
from shield.actions import Actions, ApprovalRequired
from shield.registry import Registry
from shield.schemas import Decision, PolicyDecision
from shield.sdk.pending import PendingRegistry


def _plan(*targets: str, action: str = "rotate_token") -> dict:
    return {
        "summary": "plan",
        "steps": [{"action": action, "target": t, "requires_approval": True} for t in targets],
    }


def _actions() -> tuple[Actions, ApprovalBroker]:
    registry = Registry(":memory:")
    registry.create_token("bodega", "crew")
    registry.create_token("compras", "crew")
    broker = ApprovalBroker()
    return Actions(registry=registry, approvals=broker.registry), broker


def _approved(broker: ApprovalBroker, *targets: str, action: str = "rotate_token") -> str:
    req = broker.request(_plan(*targets, action=action))
    broker.approve(req.approval_id, nonce=req.nonce)
    return req.approval_id


# -- nonce ---------------------------------------------------------------------------


def test_aprobar_sin_nonce_o_con_nonce_ajeno_falla_y_sigue_pendiente():
    broker = ApprovalBroker()
    a = broker.request(_plan("bodega"))
    b = broker.request(_plan("compras"))
    for nonce in (None, "", "otro", a.nonce):
        with pytest.raises(ApprovalRejected) as exc:
            broker.approve(b.approval_id, nonce=nonce)
        assert exc.value.code == "nonce_invalid"
    assert broker.get(b.approval_id).status == "pending"
    assert not broker.registry.get(b.approval_id).status == "approved"


def test_nonce_no_viaja_en_la_vista_publica():
    req = ApprovalBroker().request(_plan("bodega"))
    assert req.nonce and req.nonce not in str(req.public())


def test_voz_repetida_contra_otra_solicitud_no_aprueba():
    broker = ApprovalBroker()
    a = broker.request(_plan("bodega"))
    b = broker.request(_plan("compras"))
    flow = VoiceApprovalFlow(broker)
    ok = flow.handle_transcript(a.approval_id, "sí, rota el token de bodega", nonce=a.nonce)
    assert ok["status"] == "approved"
    for nonce in (None, a.nonce):
        out = flow.handle_transcript(b.approval_id, "sí, rota el token de bodega", nonce=nonce)
        assert out["status"] == "nonce_invalid"
    assert broker.get(b.approval_id).status == "pending"
    # El dueño real, con el nonce de B, sí aprueba B.
    real = flow.handle_transcript(b.approval_id, "sí, rota el token de compras", nonce=b.nonce)
    assert real["status"] == "approved"


def test_confirmar_parcial_exige_nonce_y_no_pierde_la_intencion():
    broker = ApprovalBroker()
    req = broker.request(_plan("bodega", "stripe"))
    flow = VoiceApprovalFlow(broker)
    first = flow.handle_transcript(req.approval_id, "sí, rota todo menos Stripe", nonce=req.nonce)
    assert first["status"] == "confirmation_required"
    assert flow.confirm(req.approval_id, nonce=None)["status"] == "nonce_invalid"
    assert flow.awaiting_intent(req.approval_id) is not None
    assert flow.confirm(req.approval_id, nonce=req.nonce)["status"] == "approved"
    assert broker.approved_steps_for(req.approval_id) == {("rotate_token", "bodega")}


def test_una_solicitud_se_decide_una_sola_vez():
    broker = ApprovalBroker()
    req = broker.request(_plan("bodega"))
    broker.approve(req.approval_id, nonce=req.nonce)
    with pytest.raises(ValueError):
        broker.approve(req.approval_id, nonce=req.nonce)


def test_aprobacion_caducada_no_se_acepta(monkeypatch):
    broker = ApprovalBroker()
    req = broker.request(_plan("bodega"))
    future = time.time() + 10_000
    monkeypatch.setattr("channels.approvals.time.time", lambda: future)
    with pytest.raises(ApprovalRejected) as exc:
        broker.approve(req.approval_id, nonce=req.nonce)
    assert exc.value.code == "expired"
    assert broker.get(req.approval_id).status == "expired"


# -- alcance (acción + token) y un solo uso -------------------------------------------


def test_aprobacion_no_cubre_otro_token_ni_otra_accion():
    actions, broker = _actions()
    approval_id = _approved(broker, "bodega")
    revoke_compras = actions.revoke()
    with pytest.raises(ApprovalRequired, match="no cubre"):
        revoke_compras.apply(revoke_compras.plan(agent="compras"), approval_id=approval_id)
    rotate_compras = actions.rotate_token(grace_s=0)
    with pytest.raises(ApprovalRequired, match="no cubre"):
        rotate_compras.apply(rotate_compras.plan(agent="compras"), approval_id=approval_id)
    # Nada se tocó: compras sigue activo.
    assert actions.agent_health("compras")


def test_aprobacion_se_gasta_una_vez_por_paso():
    actions, broker = _actions()
    approval_id = _approved(broker, "bodega")
    rotate = actions.rotate_token(grace_s=0)
    first = rotate.apply(rotate.plan(agent="bodega"), approval_id=approval_id)
    assert first.status == "applied"
    again = actions.rotate_token(grace_s=0)
    with pytest.raises(ApprovalRequired, match="ya usado"):
        again.apply(again.plan(agent="bodega"), approval_id=approval_id)


def test_aprobacion_parcial_solo_cubre_los_pasos_aprobados():
    actions, broker = _actions()
    req = broker.request(_plan("bodega", "compras"))
    broker.approve(req.approval_id, nonce=req.nonce, exclude_targets=["compras"])
    rotate = actions.rotate_token(grace_s=0)
    with pytest.raises(ApprovalRequired, match="no cubre"):
        rotate.apply(rotate.plan(agent="compras"), approval_id=req.approval_id)
    assert (
        rotate.apply(rotate.plan(agent="bodega"), approval_id=req.approval_id).status == "applied"
    )


def test_aprobacion_pendiente_o_rechazada_no_ejecuta():
    actions, broker = _actions()
    req = broker.request(_plan("bodega"))
    rotate = actions.rotate_token(grace_s=0)
    with pytest.raises(ApprovalRequired):
        rotate.apply(rotate.plan(agent="bodega"), approval_id=req.approval_id)
    broker.reject(req.approval_id)
    with pytest.raises(ApprovalRequired):
        rotate.apply(rotate.plan(agent="bodega"), approval_id=req.approval_id)


def test_aprobacion_caducada_no_ejecuta():
    registry = Registry(":memory:")
    registry.create_token("bodega", "crew")
    pendings = PendingRegistry()
    pending = pendings.add(
        agent="bodega",
        tool="rotate_token",
        args={},
        decision=PolicyDecision(decision=Decision.ASK_OWNER, reason="x", evidence=[]),
    )
    pendings.approve(pending.pending_id)
    pending.expires_at = time.time() - 1
    actions = Actions(registry=registry, approvals=pendings)
    rotate = actions.rotate_token(grace_s=0)
    with pytest.raises(ApprovalRequired, match="caducado"):
        rotate.apply(rotate.plan(agent="bodega"), approval_id=pending.pending_id)


def test_pending_sin_alcance_explicito_cubre_solo_su_tool_y_agente():
    pendings = PendingRegistry()
    pending = pendings.add(
        agent="bodega",
        tool="rotate_token",
        args={},
        decision=PolicyDecision(decision=Decision.ASK_OWNER, reason="x", evidence=[]),
    )
    pendings.approve(pending.pending_id)
    from shield.sdk.pending import ApprovalDenied

    with pytest.raises(ApprovalDenied):
        pendings.consume(pending.pending_id, "revoke", "bodega")
    with pytest.raises(ApprovalDenied):
        pendings.consume(pending.pending_id, "rotate_token", "compras")
    pendings.consume(pending.pending_id, "rotate_token", "bodega")
