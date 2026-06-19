from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..repositories import CostItemRepository


class CostItemSeeder:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.cost_items = CostItemRepository(connection)

    def seed_file(self, path: str | Path) -> dict[str, Any]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return self.seed_data(payload)

    def seed_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("cost_items")
        if not isinstance(items, list):
            raise ValueError("missing or invalid 'cost_items' list")

        created = 0
        updated = 0
        errors: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            try:
                self._validate_item(item, index)
                existed = self.connection.execute(
                    "SELECT id FROM cost_item WHERE code = ?",
                    (item["code"],),
                ).fetchone()
                self.cost_items.upsert(
                    code=item["code"],
                    name=item["name"],
                    discipline=item.get("discipline"),
                    class_code=item["class_code"],
                    spec_pattern=item.get("spec_pattern"),
                    unit=item["unit"],
                    unit_price_material=float(item.get("unit_price_material", 0)),
                    unit_price_labor=float(item.get("unit_price_labor", 0)),
                    unit_price_machine=float(item.get("unit_price_machine", 0)),
                    currency=item.get("currency", "CNY"),
                    region=item.get("region"),
                    version=item.get("version"),
                    effective_from=item.get("effective_from"),
                    effective_to=item.get("effective_to"),
                    description=item.get("description"),
                    status=item.get("status", "active"),
                )
                if existed:
                    updated += 1
                else:
                    created += 1
            except Exception as exc:
                errors.append({"index": index, "code": item.get("code"), "error": str(exc)})

        return {
            "total": len(items),
            "created": created,
            "updated": updated,
            "errors": errors,
        }

    @staticmethod
    def _validate_item(item: dict[str, Any], index: int) -> None:
        for field in ("code", "name", "class_code", "unit"):
            if not item.get(field):
                raise ValueError(f"cost_items[{index}]: missing '{field}'")
        for field in ("unit_price_material", "unit_price_labor", "unit_price_machine"):
            if float(item.get(field, 0)) < 0:
                raise ValueError(f"cost_items[{index}]: '{field}' must be non-negative")
