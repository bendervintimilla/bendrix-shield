"""País de origen por IP: GeoLite2 si hay base local, si no ``None``.

Sin base (``SHIELD_GEOLITE_DB``) o sin ``maxminddb`` no se inventa un país.
En modo sandbox el gateway acepta el header ``X-Demo-Country`` (solo demo).
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path


def country_for_ip(ip: str | None, db_path: str | Path | None = None) -> str | None:
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.is_private or addr.is_loopback:
        return None
    path = db_path or os.environ.get("SHIELD_GEOLITE_DB")
    if not path or not Path(path).is_file():
        return None
    try:
        import maxminddb
    except ImportError:
        return None
    try:
        with maxminddb.open_database(str(path)) as reader:
            record = reader.get(ip)
    except Exception:
        return None
    if isinstance(record, dict):
        country = record.get("country") or {}
        if isinstance(country, dict):
            return country.get("iso_code")
    return None
