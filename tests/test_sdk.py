import pytest
from openai import OpenAI

import bendrix_shield
import shield


class FakeClient:
    pass


def test_wrap_sets_gateway_and_token_on_fake_client():
    client = FakeClient()
    out = bendrix_shield.wrap(client, "shd_bodega_abc123")
    assert out is client
    assert client.api_key == "shd_bodega_abc123"
    assert str(client.base_url).rstrip("/") == "http://127.0.0.1:8000/v1"


def test_wrap_on_real_openai_client_and_shield_alias():
    client = OpenAI(api_key="placeholder")
    out = shield.wrap(client, "shd_compras_xyz789", base_url="http://localhost:9000/v1")
    assert out.api_key == "shd_compras_xyz789"
    assert str(out.base_url).rstrip("/") == "http://localhost:9000/v1"


def test_wrap_rejects_missing_or_foreign_token():
    with pytest.raises(ValueError):
        bendrix_shield.wrap(FakeClient())
    with pytest.raises(ValueError):
        bendrix_shield.wrap(FakeClient(), "sk-live-not-a-shield-token")
