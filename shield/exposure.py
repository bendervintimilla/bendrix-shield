"""`ThreatCard × Asset → Exposure` con razón y confianza (H5 lo completa)."""

from __future__ import annotations

from shield.schemas import Asset, Exposure, ThreatCard


def match(threat: ThreatCard, assets: list[Asset]) -> list[Exposure]:
    """Cruce determinista por nombre de producto; H5 suma el triaje con modelos."""
    found: list[Exposure] = []
    product_names = {p.name.lower() for p in threat.products}
    for asset in assets:
        if asset.name.lower() in product_names:
            found.append(
                Exposure(
                    threat_id=threat.id,
                    asset_id=asset.id,
                    reason=f"asset name matches product '{asset.name}'",
                    confidence=0.5,
                )
            )
    return found
