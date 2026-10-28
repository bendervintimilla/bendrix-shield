"""Ledger SQLite de Compras: insumos, proveedores, compras y recetas.

Un solo archivo SQLite (o ``:memory:`` en tests). Sin datos de producción:
todo lo que entra aquí viene de facturas sintéticas o de la demo.

- ``items``/``inventory``: insumo con stock y **costo promedio ponderado**.
  Al registrar una compra: ``nuevo_prom = (stock*prom + qty*precio) /
  (stock + qty)`` y ``stock += qty``.
- ``suppliers``: proveedor con su **cuenta de pago** (campo sensible: solo
  se cambia vía la herramienta ``update_supplier_account``, con política).
- ``purchases``: cabecera de compra con ``content_hash`` único. Registrar
  la misma factura dos veces es **idempotente**: devuelve la compra ya
  creada y no duplica stock ni costo.
- ``recipes``: recetas de **1 nivel** (plato -> insumos directos).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


def invoice_content_hash(payload: dict[str, Any]) -> str:
    """Hash canónico de una factura extraída (para idempotencia)."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    payment_account TEXT,
    payment_label TEXT
);
CREATE TABLE IF NOT EXISTS items (
    sku TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT 'unidad'
);
CREATE TABLE IF NOT EXISTS inventory (
    sku TEXT PRIMARY KEY REFERENCES items(sku),
    qty REAL NOT NULL DEFAULT 0,
    avg_cost REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER REFERENCES suppliers(id),
    invoice_number TEXT,
    invoice_date TEXT,
    currency TEXT NOT NULL DEFAULT 'USD',
    subtotal REAL NOT NULL DEFAULT 0,
    tax REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS purchase_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL REFERENCES purchases(id),
    sku TEXT NOT NULL,
    qty REAL NOT NULL,
    unit_price REAL NOT NULL,
    line_total REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS recipes (
    dish TEXT NOT NULL,
    sku TEXT NOT NULL,
    qty_per_dish REAL NOT NULL,
    unit TEXT NOT NULL DEFAULT 'unidad',
    PRIMARY KEY (dish, sku)
);
"""


class Ledger:
    """Ledger de Compras respaldado en SQLite."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._path = str(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Ledger:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- proveedores e insumos -------------------------------------------
    def upsert_supplier(
        self, name: str, *, payment_account: str | None = None, payment_label: str | None = None
    ) -> dict[str, Any]:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO suppliers(name, payment_account, payment_label) VALUES (?,?,?)"
                " ON CONFLICT(name) DO UPDATE SET"
                " payment_account=COALESCE(excluded.payment_account, suppliers.payment_account),"
                " payment_label=COALESCE(excluded.payment_label, suppliers.payment_label)",
                (name, payment_account, payment_label),
            )
        return self.get_supplier(name)  # type: ignore[return-value]

    def get_supplier(self, name_or_id: str | int) -> dict[str, Any] | None:
        with self._lock:
            if isinstance(name_or_id, int):
                row = self._conn.execute(
                    "SELECT * FROM suppliers WHERE id=?", (name_or_id,)
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT * FROM suppliers WHERE name=?", (name_or_id,)
                ).fetchone()
        return dict(row) if row else None

    def list_suppliers(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def set_supplier_account(self, supplier_id: int, payment_account: str) -> dict[str, Any]:
        """Cambia la cuenta de pago. Solo lo llama la tool con política."""
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE suppliers SET payment_account=? WHERE id=?", (payment_account, supplier_id)
            )
            if cur.rowcount == 0:
                raise KeyError(f"proveedor inexistente: {supplier_id}")
        return self.get_supplier(supplier_id)  # type: ignore[return-value]

    def upsert_item(self, sku: str, name: str, unit: str = "unidad") -> dict[str, Any]:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO items(sku, name, unit) VALUES (?,?,?)"
                " ON CONFLICT(sku) DO UPDATE SET name=excluded.name, unit=excluded.unit",
                (sku, name, unit),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO inventory(sku, qty, avg_cost) VALUES (?, 0, 0)", (sku,)
            )
        return {"sku": sku, "name": name, "unit": unit}

    # -- compras -----------------------------------------------------------
    def record_purchase(
        self,
        *,
        supplier: str,
        lines: list[dict[str, Any]],
        invoice_number: str | None = None,
        invoice_date: str | None = None,
        currency: str = "USD",
        subtotal: float = 0.0,
        tax: float = 0.0,
        total: float = 0.0,
        content_hash: str | None = None,
    ) -> dict[str, Any]:
        """Registra una compra. Idempotente por ``content_hash``.

        Devuelve ``{purchase_id, created, content_hash, ...}``. Si el hash
        ya existe, ``created`` es False y no se toca el inventario.
        """
        payload = {
            "supplier": supplier,
            "invoice_number": invoice_number,
            "invoice_date": invoice_date,
            "currency": currency,
            "lines": [
                {
                    "sku": str(
                        line.get("sku") or line.get("item") or line.get("description") or ""
                    ),
                    "qty": float(line.get("qty") or 0),
                    "unit_price": float(line.get("unit_price") or line.get("price") or 0),
                }
                for line in lines
            ],
            "subtotal": float(subtotal),
            "tax": float(tax),
            "total": float(total),
        }
        digest = content_hash or invoice_content_hash(payload)
        with self._lock:
            existing = self._conn.execute(
                "SELECT * FROM purchases WHERE content_hash=?", (digest,)
            ).fetchone()
        if existing is not None:
            return {**dict(existing), "created": False, "content_hash": digest}

        supplier_row = self.upsert_supplier(supplier)
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO purchases(supplier_id, invoice_number, invoice_date, currency,"
                " subtotal, tax, total, content_hash) VALUES (?,?,?,?,?,?,?,?)",
                (
                    supplier_row["id"],
                    invoice_number,
                    invoice_date,
                    currency,
                    float(subtotal),
                    float(tax),
                    float(total),
                    digest,
                ),
            )
            purchase_id = int(cur.lastrowid)
            for line in lines:
                sku = str(line.get("sku") or line.get("item") or line.get("description") or "")
                if not sku:
                    continue
                qty = float(line.get("qty") or 0)
                price = float(line.get("unit_price") or line.get("price") or 0)
                name = str(line.get("description") or line.get("name") or sku)
                unit = str(line.get("unit") or "unidad")
                self._conn.execute(
                    "INSERT INTO items(sku, name, unit) VALUES (?,?,?) ON CONFLICT(sku) DO NOTHING",
                    (sku, name, unit),
                )
                self._conn.execute(
                    "INSERT OR IGNORE INTO inventory(sku, qty, avg_cost) VALUES (?, 0, 0)", (sku,)
                )
                inv = self._conn.execute(
                    "SELECT qty, avg_cost FROM inventory WHERE sku=?", (sku,)
                ).fetchone()
                old_qty, old_avg = float(inv["qty"]), float(inv["avg_cost"])
                new_qty = old_qty + qty
                new_avg = ((old_qty * old_avg) + (qty * price)) / new_qty if new_qty else 0.0
                self._conn.execute(
                    "UPDATE inventory SET qty=?, avg_cost=? WHERE sku=?", (new_qty, new_avg, sku)
                )
                self._conn.execute(
                    "INSERT INTO purchase_lines(purchase_id, sku, qty, unit_price, line_total)"
                    " VALUES (?,?,?,?,?)",
                    (purchase_id, sku, qty, price, qty * price),
                )
        row = self.get_purchase(purchase_id)
        return {**(row or {}), "created": True, "content_hash": digest}

    def get_purchase(self, purchase_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM purchases WHERE id=?", (purchase_id,)
            ).fetchone()
            if row is None:
                return None
            lines = self._conn.execute(
                "SELECT sku, qty, unit_price, line_total FROM purchase_lines"
                " WHERE purchase_id=? ORDER BY id",
                (purchase_id,),
            ).fetchall()
        return {**dict(row), "lines": [dict(line) for line in lines]}

    def list_purchases(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM purchases ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    # -- inventario teórico y recetas --------------------------------------
    def inventory(self, sku: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if sku:
                rows = self._conn.execute(
                    "SELECT i.sku, i.name, i.unit, inv.qty, inv.avg_cost"
                    " FROM items i JOIN inventory inv ON inv.sku=i.sku WHERE i.sku=?",
                    (sku,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT i.sku, i.name, i.unit, inv.qty, inv.avg_cost"
                    " FROM items i JOIN inventory inv ON inv.sku=i.sku ORDER BY i.sku"
                ).fetchall()
        return [dict(r) for r in rows]

    def theoretical_stock(self, sku: str) -> float:
        rows = self.inventory(sku)
        return float(rows[0]["qty"]) if rows else 0.0

    def define_recipe(self, dish: str, components: list[dict[str, Any]]) -> None:
        """Receta de 1 nivel: plato -> lista de {sku, qty_per_dish, unit}."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM recipes WHERE dish=?", (dish,))
            for comp in components:
                sku = str(comp["sku"])
                self._conn.execute(
                    "INSERT OR IGNORE INTO items(sku, name, unit) VALUES (?,?,?)",
                    (sku, str(comp.get("name") or sku), str(comp.get("unit") or "unidad")),
                )
                self._conn.execute(
                    "INSERT OR IGNORE INTO inventory(sku, qty, avg_cost) VALUES (?, 0, 0)", (sku,)
                )
                self._conn.execute(
                    "INSERT INTO recipes(dish, sku, qty_per_dish, unit) VALUES (?,?,?,?)",
                    (
                        dish,
                        sku,
                        float(comp.get("qty_per_dish", comp.get("qty", 0))),
                        str(comp.get("unit") or "unidad"),
                    ),
                )

    def recipe(self, dish: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT sku, qty_per_dish, unit FROM recipes WHERE dish=? ORDER BY sku", (dish,)
            ).fetchall()
        return [dict(r) for r in rows]

    def recipe_cost(self, dish: str) -> dict[str, Any]:
        """Costo del plato con el promedio ponderado vigente (1 nivel)."""
        lines: list[dict[str, Any]] = []
        missing: list[str] = []
        total = 0.0
        for comp in self.recipe(dish):
            inv = self.inventory(comp["sku"])
            avg = float(inv[0]["avg_cost"]) if inv else 0.0
            if not inv:
                missing.append(comp["sku"])
            line_cost = float(comp["qty_per_dish"]) * avg
            total += line_cost
            lines.append(
                {
                    "sku": comp["sku"],
                    "qty_per_dish": float(comp["qty_per_dish"]),
                    "unit": comp["unit"],
                    "avg_cost": avg,
                    "line_cost": line_cost,
                }
            )
        return {"dish": dish, "total_cost": total, "lines": lines, "missing": missing}
