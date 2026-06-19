from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..repositories import BudgetItemRepository, CostItemRepository


class BudgetGenerator:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.budget_items = BudgetItemRepository(connection)
        self.cost_items = CostItemRepository(connection)

    def generate(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> dict[str, Any]:
        cleared = self.budget_items.clear_auto(project_id=project_id, drawing_id=drawing_id)
        quantities = self._load_quantities(project_id=project_id, drawing_id=drawing_id)
        summary = {
            "quantities_total": len(quantities),
            "created": 0,
            "matched": 0,
            "unmatched": 0,
            "review": 0,
            "cleared": cleared,
            "total_cost": 0.0,
        }

        for quantity in quantities:
            match = self._best_match(quantity)
            if match:
                row = self._matched_row(quantity, match)
                summary["matched"] += 1
                if row["status"] == "review":
                    summary["review"] += 1
            else:
                row = self._unmatched_row(quantity)
                summary["unmatched"] += 1
                if row["status"] == "review":
                    summary["review"] += 1
            self.budget_items.create(**row)
            summary["created"] += 1
            summary["total_cost"] += row["total_cost"]

        summary["total_cost"] = round(summary["total_cost"], 6)
        return summary

    def _load_quantities(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions = ["status != 'rejected'"]
        params: list[Any] = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if drawing_id:
            conditions.append("drawing_id = ?")
            params.append(drawing_id)
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM quantity_item
            WHERE {' AND '.join(conditions)}
            ORDER BY class_code, group_key, source_object_id, id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def _best_match(self, quantity: dict[str, Any]) -> dict[str, Any] | None:
        matches = self.cost_items.find_matches(quantity["class_code"], quantity["unit"])
        if not matches:
            return None
        spec = quantity.get("spec") or ""
        with_spec = [
            item
            for item in matches
            if item.get("spec_pattern") and item["spec_pattern"] in spec
        ]
        empty_spec = [item for item in matches if not item.get("spec_pattern")]
        candidates = with_spec or empty_spec or matches
        return sorted(candidates, key=lambda item: item["code"])[0]

    def _matched_row(self, quantity: dict[str, Any], cost: dict[str, Any]) -> dict[str, Any]:
        costs = self._costs(quantity, cost)
        manual_review = quantity["quantity_method"] == "manual_review"
        status = "review" if manual_review else "matched"
        return {
            "project_id": quantity["project_id"],
            "drawing_id": quantity["drawing_id"],
            "quantity_item_id": quantity["id"],
            "cost_item_id": cost["id"],
            "class_code": quantity["class_code"],
            "discipline": quantity["discipline"] or cost["discipline"],
            "item_name": quantity["item_name"],
            "spec": quantity["spec"],
            "unit": quantity["unit"],
            "quantity": float(quantity["quantity"]),
            "unit_price_material": float(cost["unit_price_material"]),
            "unit_price_labor": float(cost["unit_price_labor"]),
            "unit_price_machine": float(cost["unit_price_machine"]),
            "material_cost": costs["material_cost"],
            "labor_cost": costs["labor_cost"],
            "machine_cost": costs["machine_cost"],
            "total_cost": costs["total_cost"],
            "pricing_source": "cost_item",
            "confidence": float(quantity["confidence"] or 1.0),
            "status": status,
            "evidence": self._evidence(
                quantity=quantity,
                cost=cost,
                match_method="class_code_unit",
                match_score=1.0,
                reason="quantity requires manual review" if manual_review else None,
            ),
        }

    def _unmatched_row(self, quantity: dict[str, Any]) -> dict[str, Any]:
        confidence = min(float(quantity["confidence"] or 1.0), 0.5)
        return {
            "project_id": quantity["project_id"],
            "drawing_id": quantity["drawing_id"],
            "quantity_item_id": quantity["id"],
            "cost_item_id": None,
            "class_code": quantity["class_code"],
            "discipline": quantity["discipline"],
            "item_name": quantity["item_name"],
            "spec": quantity["spec"],
            "unit": quantity["unit"],
            "quantity": float(quantity["quantity"]),
            "unit_price_material": 0,
            "unit_price_labor": 0,
            "unit_price_machine": 0,
            "material_cost": 0,
            "labor_cost": 0,
            "machine_cost": 0,
            "total_cost": 0,
            "pricing_source": "unmatched",
            "confidence": confidence,
            "status": "unmatched",
            "evidence": self._evidence(
                quantity=quantity,
                cost=None,
                match_method="none",
                match_score=0,
                reason="no active cost item matched class_code and unit",
            ),
        }

    @staticmethod
    def _costs(quantity: dict[str, Any], cost: dict[str, Any]) -> dict[str, float]:
        qty = float(quantity["quantity"])
        material = qty * float(cost["unit_price_material"])
        labor = qty * float(cost["unit_price_labor"])
        machine = qty * float(cost["unit_price_machine"])
        return {
            "material_cost": material,
            "labor_cost": labor,
            "machine_cost": machine,
            "total_cost": material + labor + machine,
        }

    @staticmethod
    def _evidence(
        quantity: dict[str, Any],
        cost: dict[str, Any] | None,
        match_method: str,
        match_score: float,
        reason: str | None = None,
    ) -> dict[str, Any]:
        evidence = {
            "quantity_item_id": quantity["id"],
            "quantity_method": quantity["quantity_method"],
            "quantity_evidence": json.loads(quantity["evidence_json"]) if quantity.get("evidence_json") else {},
            "match_method": match_method,
            "match_score": match_score,
            "matched_fields": ["class_code", "unit"] if cost else [],
        }
        if cost:
            evidence.update(
                {
                    "cost_item_id": cost["id"],
                    "cost_item_code": cost["code"],
                    "spec_pattern": cost.get("spec_pattern"),
                }
            )
        if reason:
            evidence["reason"] = reason
        return evidence
