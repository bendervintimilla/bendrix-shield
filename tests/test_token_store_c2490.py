"""C2490 e: token store con un archivo por agente (cierra rt-host-store-shared)."""

from __future__ import annotations

import json
import os

import pytest

from shield.sdk.token_store import LocalTokenStore


def _mode(path) -> int:
    return path.stat().st_mode & 0o777


def test_un_archivo_por_agente_con_permisos(tmp_path):
    store = LocalTokenStore(tmp_path / "agent-tokens.json")
    store.set_token("bodega", "shd_bodega_demo001", "tid_b")
    store.set_token("compras", "shd_compras_demo002", "tid_c")
    fb, fc = store.path_for("bodega"), store.path_for("compras")
    assert fb.parent == fc.parent == tmp_path / "agent-tokens.d"
    assert fb.name == "bodega.json" and fc.name == "compras.json"
    assert "shd_compras" not in fb.read_text(encoding="utf-8")
    assert _mode(fb) == 0o600 and _mode(fc) == 0o600
    assert _mode(store.dir) == 0o700
    assert not (tmp_path / "agent-tokens.json").exists()
    assert store.get_token("bodega") == "shd_bodega_demo001"
    assert store.get_token_id("compras") == "tid_c"


def test_store_ligado_no_lee_ni_escribe_otro_agente(tmp_path):
    base = tmp_path / "agent-tokens.json"
    LocalTokenStore(base).set_token("compras", "shd_compras_demo002")
    bodega = LocalTokenStore(base, agent="bodega")
    bodega.set_token("bodega", "shd_bodega_demo001")
    assert bodega.get_token("bodega") == "shd_bodega_demo001"
    with pytest.raises(PermissionError):
        bodega.get_token("compras")
    with pytest.raises(PermissionError):
        bodega.get_token_id("compras")
    with pytest.raises(PermissionError):
        bodega.set_token("compras", "shd_compras_pisado")
    with pytest.raises(PermissionError):
        bodega.path_for("compras")
    assert LocalTokenStore(base).get_token("compras") == "shd_compras_demo002"


@pytest.mark.parametrize("agent", ["../compras", "a/b", ".oculto", "", "x" * 65])
def test_agent_id_invalido(tmp_path, agent):
    store = LocalTokenStore(tmp_path / "t.json")
    with pytest.raises(ValueError):
        store.set_token(agent, "shd_x_demo")


def test_migra_formato_viejo_sin_exponer_otros(tmp_path):
    legacy = tmp_path / "agent-tokens.json"
    legacy.write_text(
        json.dumps(
            {
                "bodega": {"token": "shd_bodega_viejo", "token_id": "tid_b"},
                "compras": {"token": "shd_compras_viejo", "token_id": "tid_c"},
            }
        ),
        encoding="utf-8",
    )
    os.chmod(legacy, 0o600)
    bodega = LocalTokenStore(legacy, agent="bodega")
    assert bodega.get_token("bodega") == "shd_bodega_viejo"
    assert bodega.get_token_id("bodega") == "tid_b"
    # La entrada de bodega pasó a su archivo y salió del JSON viejo.
    assert _mode(bodega.path_for("bodega")) == 0o600
    resto = json.loads(legacy.read_text(encoding="utf-8"))
    assert list(resto) == ["compras"]
    with pytest.raises(PermissionError):
        bodega.get_token("compras")
    # El guardián migra el último y el JSON viejo desaparece.
    guardian = LocalTokenStore(legacy)
    assert guardian.get_token("compras") == "shd_compras_viejo"
    assert not legacy.exists()


def test_set_token_quita_la_entrada_vieja(tmp_path):
    legacy = tmp_path / "agent-tokens.json"
    legacy.write_text(json.dumps({"bodega": {"token": "shd_bodega_viejo"}}), encoding="utf-8")
    store = LocalTokenStore(legacy)
    store.set_token("bodega", "shd_bodega_nuevo")
    assert not legacy.exists()
    assert store.get_token("bodega") == "shd_bodega_nuevo"


def test_ruta_de_directorio(tmp_path):
    store = LocalTokenStore(tmp_path / "tokens")
    store.set_token("bodega", "shd_bodega_demo001")
    assert store.path_for("bodega") == tmp_path / "tokens" / "bodega.json"
    assert store.legacy_path is None
    assert LocalTokenStore(tmp_path / "tokens").get_token("compras") is None


def test_rechaza_token_sin_prefijo(tmp_path):
    with pytest.raises(ValueError):
        LocalTokenStore(tmp_path / "t.json").set_token("bodega", "sk-real")
