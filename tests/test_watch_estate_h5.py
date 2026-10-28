import json

import httpx
import pytest

from shield.estate import (
    GatewayRegistryConnector,
    GcpApiKeysConnector,
    GithubSbomConnector,
    RailwayConnector,
    WebAllowlistConnector,
)
from shield.meta_client import NeedsCredits
from shield.registry import Registry
from shield.watch import FeedCache, fetch_feed, parse_kev, parse_osv, parse_rss, parse_status
from shield.watch.manual import from_image, from_text


def test_parse_kev_osv_rss_status():
    kev = parse_kev(
        {
            "vulnerabilities": [
                {
                    "cveID": "CVE-2026-1",
                    "vendorProject": "PHP",
                    "product": "PHP",
                    "dateAdded": "2026-10-13",
                    "requiredAction": "upgrade",
                }
            ]
        }
    )
    assert kev[0].id == "CVE-2026-1" and kev[0].products[0].name == "PHP"
    osv = parse_osv(
        {
            "vulns": [
                {
                    "id": "GHSA-xxxx",
                    "published": "2026-10-01T00:00:00Z",
                    "affected": [
                        {
                            "package": {"name": "litellm", "ecosystem": "pypi"},
                            "versions": ["1.82.7"],
                            "ranges": [{"events": [{"introduced": "0"}, {"fixed": "1.82.9"}]}],
                        }
                    ],
                }
            ]
        }
    )
    assert osv[0].products[0].affected_versions == ["1.82.7"]
    assert osv[0].products[0].fixed_versions == ["1.82.9"]
    rss = parse_rss(
        '<?xml version="1.0"?><rss><channel><item><title>Aviso PHP</title>'
        "<link>https://example.com/a</link><pubDate>Wed, 21 Oct 2026 00:00:00 GMT</pubDate>"
        "</item></channel></rss>",
        source_url="https://example.com/feed",
    )
    assert rss[0].source_url == "https://example.com/a" and rss[0].published_at is not None
    status = parse_status(
        {
            "page": {"name": "Railway"},
            "incidents": [
                {
                    "id": "i1",
                    "name": "env exposure",
                    "impact": "major",
                    "created_at": "2026-10-21T00:00:00Z",
                }
            ],
        },
        source_url="https://status.example.com",
    )
    assert status[0].severity == "high" and status[0].products[0].ecosystem == "platform"


def test_fetch_feed_uses_cache_without_second_network_call(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={
                "vulnerabilities": [{"cveID": "CVE-2026-9", "product": "X", "vendorProject": "Y"}]
            },
        )

    cache = FeedCache(tmp_path)
    transport = httpx.MockTransport(handler)
    first = fetch_feed("https://example.com/kev.json", "kev", cache=cache, transport=transport)
    second = fetch_feed("https://example.com/kev.json", "kev", cache=cache, transport=transport)
    assert calls["n"] == 1 and first[0].id == second[0].id == "CVE-2026-9"


class _NeedsCreditsClient:
    def chat_completions(self, **kwargs):
        raise NeedsCredits(402, "billing_not_configured")

    def close(self):
        pass


class _SparkClient:
    def __init__(self):
        self.cost_usd = 0.0

    def chat_completions(self, **kwargs):
        assert kwargs["model"] == "muse-spark-1.3"
        content = json.dumps(
            {
                "id": "CVE-2026-77",
                "severity": "critical",
                "products": [
                    {
                        "name": "LiteLLM",
                        "ecosystem": "pypi",
                        "affected_versions": ["1.82.7"],
                        "fixed_versions": ["1.82.9"],
                    }
                ],
                "iocs": [],
                "actions": ["upgrade"],
            }
        )
        from types import SimpleNamespace

        return SimpleNamespace(
            data={"choices": [{"message": {"content": content}}]}, cost_usd=0.001
        )

    def close(self):
        pass


def test_manual_spark_and_needs_credits_fallback():
    result = from_text(
        "LiteLLM 1.82.7 vulnerable", source_url="https://example.com/x", client=_SparkClient()
    )
    assert result.via == "spark" and result.card.products[0].name == "LiteLLM"
    fallback = from_text(
        "Aviso crítico CVE-2026-1234 en el producto",
        source_url="https://e.com",
        client=_NeedsCreditsClient(),
    )
    assert fallback.via == "fallback" and fallback.needs_credits is True
    assert fallback.card.id == "CVE-2026-1234" and fallback.card.severity == "critical"
    image = from_image(b"\x89PNG fake", source_url="https://e.com", client=_NeedsCreditsClient())
    assert image.via == "fallback"


def test_estate_connectors_are_read_only_and_secret_free():
    registry = Registry(":memory:")
    token, _raw = registry.create_token("bodega", "crew", models=["sam-3.1"])
    assets = GatewayRegistryConnector(registry).list_assets()
    assert assets[0].id == token.token_id and "sam-3.1" in assets[0].metadata["models"]
    assert _raw not in json.dumps([a.model_dump() for a in assets])

    railway = RailwayConnector(
        lambda: {"api": {"META_MODEL_API_KEY": "sk-no-sale", "PORT": "8000"}}
    )
    rel = railway.list_assets()
    assert rel[0].metadata["var_names"] == "META_MODEL_API_KEY,PORT"
    assert "sk-no-sale" not in json.dumps([a.model_dump() for a in rel])

    gcp = GcpApiKeysConnector(
        lambda: [
            {
                "display_name": "k1",
                "last4": "1234",
                "restrictions": {"api": ["ai"]},
                "usage": {"calls": 3},
            }
        ]
    )
    assert gcp.list_assets()[0].last4 == "1234"
    with pytest.raises(ValueError):
        GcpApiKeysConnector(lambda: [], project="otro-proyecto")

    sbom = GithubSbomConnector(
        {
            "package-lock.json": json.dumps(
                {"packages": {"": {}, "node_modules/litellm": {"version": "1.82.7"}}}
            ),
            "requirements.txt": "litellm==1.82.7\nflask>=3.0\n",
        }
    ).list_assets()
    assert {(a.name, a.metadata["version"]) for a in sbom} >= {
        ("litellm", "1.82.7"),
        ("flask", "3.0"),
    }

    web = WebAllowlistConnector(
        ["https://cantina-demo.bendrix.test/"],
        allowlist=["cantina-demo.bendrix.test"],
        fetcher=lambda url: ({"X-Powered-By": "PHP/8.1.20"}, "<html></html>"),
    )
    assert web.list_assets()[0].metadata["version"] == "8.1.20"
    with pytest.raises(ValueError):
        WebAllowlistConnector(
            ["https://example.com/"],
            allowlist=["cantina-demo.bendrix.test"],
            fetcher=lambda url: ({}, ""),
        )
    registry.close()
