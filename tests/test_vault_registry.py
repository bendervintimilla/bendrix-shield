import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace

from shield.registry import Registry
from shield.schemas import AgentTokenStatus, CallLog, Decision
from shield.vault import MemoryVault, get_vault
from shield.vault.keychain import KeychainVault
from shield.vault.secret_manager import SecretManagerVault


def test_memory_vault_roundtrip_and_masking():
    vault = MemoryVault()
    assert vault.get("META_MODEL_API_KEY") is None
    vault.put("META_MODEL_API_KEY", "real-key-value-9876")
    assert vault.get("META_MODEL_API_KEY") == "real-key-value-9876"
    assert (
        vault.fingerprint("META_MODEL_API_KEY")
        == hashlib.sha256(b"real-key-value-9876").hexdigest()[:8]
    )
    assert vault.last4("META_MODEL_API_KEY") == "9876"
    assert "real-key-value" not in repr(vault)
    assert vault.describe("META_MODEL_API_KEY")["last4"] == "9876"


def test_keychain_vault_with_fake_runner():
    store = {}

    def runner(args, **kwargs):
        if args[1] == "add-generic-password":
            store[args[args.index("-s") + 1]] = args[-1]
            return SimpleNamespace(returncode=0, stdout="")
        value = store.get(args[args.index("-s") + 1])
        return SimpleNamespace(returncode=0 if value else 44, stdout=(value or "") + "\n")

    vault = KeychainVault(runner=runner)
    vault.put("META_MODEL_API_KEY", "keychain-value-4321")
    assert vault.get("META_MODEL_API_KEY") == "keychain-value-4321"
    assert vault.last4("META_MODEL_API_KEY") == "4321"
    assert vault.get("missing") is None


def test_secret_manager_vault_with_fake_client():
    class FakeClient:
        def __init__(self):
            self.values = {}

        def access_secret_version(self, request):
            value = self.values[request["name"].split("/secrets/")[1].split("/")[0]]
            return SimpleNamespace(payload=SimpleNamespace(data=value.encode()))

        def get_secret(self, request):
            name = request["name"].split("/secrets/")[1]
            if name not in self.values:
                raise RuntimeError("not found")

        def create_secret(self, request):
            self.values[request["secret_id"]] = ""

        def add_secret_version(self, request):
            name = request["parent"].split("/secrets/")[1]
            self.values[name] = request["payload"]["data"].decode()

    vault = SecretManagerVault(project="bendrix-hackathon", client=FakeClient())
    vault.put("hackathon-meta-model-api-key", "gcp-value-1111")
    assert vault.get("hackathon-meta-model-api-key") == "gcp-value-1111"
    assert get_vault("memory").get("x") is None


def test_registry_rotate_one_agent_does_not_affect_other():
    reg = Registry(":memory:")
    bodega, raw_bodega = reg.create_token("bodega", "crew", models=["sam-3.1"])
    compras, raw_compras = reg.create_token("compras", "crew", models=["muse-spark-1.3"])
    rotated, raw_new = reg.rotate(bodega.token_id)
    assert rotated is not None
    assert reg.authenticate(raw_bodega).status is AgentTokenStatus.ROTATED
    assert reg.authenticate(raw_new).status is AgentTokenStatus.ACTIVE
    # El otro agente queda intacto.
    compras_now = reg.authenticate(raw_compras)
    assert compras_now.status is AgentTokenStatus.ACTIVE
    assert compras_now.token_id == compras.token_id
    reg.close()


def test_registry_revoke_and_spend():
    reg = Registry(":memory:")
    token, raw = reg.create_token("bodega", "crew", spend_cap_usd=1.0)
    assert reg.authenticate(raw).agent == "bodega"
    assert reg.authenticate("shd_bodega_inventado") is None
    assert reg.authenticate(None) is None
    reg.record_call(
        CallLog(
            ts=datetime.now(UTC),
            agent="bodega",
            model="sam-3.1",
            cost_usd=0.75,
            latency_ms=12.0,
            decision=Decision.ALLOW,
        )
    )
    assert reg.total_spend_usd("bodega") == 0.75
    assert reg.latency_percentile(50, "bodega") == 12.0
    reg.revoke(token.token_id)
    assert reg.authenticate(raw).status is AgentTokenStatus.REVOKED
    reg.close()
