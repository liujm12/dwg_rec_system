from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..repositories import QuantityRepository


DEFAULT_PROFILE_PATH = (
    Path(__file__).resolve().parents[1]
    / "taxonomy"
    / "engineering_class_profiles.json"
)


class QuantityGenerator:
    def __init__(
        self,
        connection: sqlite3.Connection,
        profile_path: str | Path | None = None,
    ):
        self.connection = connection
        self.profile_path = Path(profile_path) if profile_path else DEFAULT_PROFILE_PATH
        self.quantities = QuantityRepository(connection)
        self.profiles = self._load_profiles(self.profile_path)

    def generate(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> dict[str, Any]:
        cleared = self.quantities.clear_auto(project_id=project_id, drawing_id=drawing_id)
        objects = self._load_objects(project_id=project_id, drawing_id=drawing_id)
        attributes = self._load_attributes([item["id"] for item in objects])

        summary = {
            "objects_total": len(objects),
            "created": 0,
            "cleared": cleared,
            "skipped_no_profile": 0,
            "skipped_no_budget": 0,
            "manual_review": 0,
        }
        pending_grouped: dict[tuple[Any, ...], dict[str, Any]] = {}

        for obj in objects:
            class_code = obj["class"]
            profile = self.profiles.get(class_code)
            if not profile:
                summary["skipped_no_profile"] += 1
                continue
            budget = profile.get("budget") or {}
            if not budget:
                summary["skipped_no_budget"] += 1
                continue

            method = budget.get("quantity_method", "manual_review")
            group_by = budget.get("group_by") or []
            object_attributes = attributes.get(obj["id"], {})
            group_key, spec, used_attributes = self._build_group(
                class_code=class_code,
                group_by=group_by,
                attributes=object_attributes,
            )

            if method == "grouped_count":
                key = (
                    obj["project_id"],
                    obj["drawing_id"],
                    class_code,
                    obj["discipline"],
                    budget.get("unit") or "pcs",
                    group_key,
                    spec,
                    profile.get("profile_group"),
                )
                bucket = pending_grouped.setdefault(
                    key,
                    {
                        "project_id": obj["project_id"],
                        "drawing_id": obj["drawing_id"],
                        "class_code": class_code,
                        "discipline": obj["discipline"],
                        "item_name": class_code,
                        "spec": spec,
                        "unit": budget.get("unit") or "pcs",
                        "quantity": 0,
                        "quantity_method": method,
                        "group_key": group_key,
                        "location": self._attribute_value(object_attributes, "location"),
                        "system_code": self._attribute_value(object_attributes, "system"),
                        "confidence_values": [],
                        "source_object_ids": [],
                        "used_attributes": used_attributes,
                        "profile_group": profile.get("profile_group"),
                    },
                )
                bucket["quantity"] += 1
                bucket["confidence_values"].append(float(obj["confidence"] or 1.0))
                bucket["source_object_ids"].append(obj["id"])
                continue

            result = self._calculate_quantity(obj, budget, method)
            if result["quantity_method"] == "manual_review":
                summary["manual_review"] += 1
            evidence = self._build_evidence(
                obj=obj,
                profile=profile,
                requested_method=method,
                actual_method=result["quantity_method"],
                used_attributes=used_attributes,
                geometry=result.get("geometry"),
                reason=result.get("reason"),
            )
            self.quantities.upsert(
                project_id=obj["project_id"],
                drawing_id=obj["drawing_id"],
                source_object_id=obj["id"],
                class_code=class_code,
                discipline=obj["discipline"],
                item_name=class_code,
                spec=spec,
                unit=budget.get("unit") or result.get("unit") or "review",
                quantity=float(result["quantity"]),
                quantity_method=result["quantity_method"],
                group_key=group_key,
                location=self._attribute_value(object_attributes, "location"),
                system_code=self._attribute_value(object_attributes, "system"),
                confidence=float(obj["confidence"] or 1.0),
                evidence=evidence,
            )
            summary["created"] += 1

        for bucket in pending_grouped.values():
            confidence_values = bucket.pop("confidence_values")
            source_object_ids = bucket.pop("source_object_ids")
            confidence = (
                sum(confidence_values) / len(confidence_values)
                if confidence_values
                else 1.0
            )
            evidence = {
                "source_object_ids": source_object_ids,
                "class_code": bucket["class_code"],
                "quantity_method": "grouped_count",
                "profile_group": bucket.pop("profile_group"),
                "used_attributes": bucket.pop("used_attributes"),
                "generator": "quantity_generator",
                "generator_version": "0.1",
            }
            self.quantities.upsert(
                **bucket,
                confidence=confidence,
                evidence=evidence,
            )
            summary["created"] += 1

        return summary

    def _load_objects(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions = ["o.status != 'rejected'"]
        params: list[Any] = []
        if project_id:
            conditions.append("d.project_id = ?")
            params.append(project_id)
        if drawing_id:
            conditions.append("o.drawing_id = ?")
            params.append(drawing_id)
        where = f"WHERE {' AND '.join(conditions)}"
        rows = self.connection.execute(
            f"""
            SELECT
                o.id,
                o.drawing_id,
                d.project_id,
                o.class,
                o.confidence,
                oc.discipline,
                g.center_x,
                g.center_y,
                g.width,
                g.height,
                g.raw_geometry_json
            FROM cad_object o
            LEFT JOIN drawing d ON d.id = o.drawing_id
            LEFT JOIN object_class oc ON oc.id = o.class_id
            LEFT JOIN geometry g ON g.object_id = o.id
            {where}
            ORDER BY o.created_at, o.id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def _load_attributes(self, object_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not object_ids:
            return {}
        placeholders = ",".join("?" for _ in object_ids)
        rows = self.connection.execute(
            f"""
            SELECT object_id, key, value, normalized_value, value_type
            FROM attribute
            WHERE object_id IN ({placeholders})
            """,
            object_ids,
        ).fetchall()
        result: dict[str, dict[str, Any]] = defaultdict(dict)
        for row in rows:
            value: Any = row["normalized_value"] if row["normalized_value"] is not None else row["value"]
            if row["value_type"] == "json" and value:
                value = json.loads(value)
            result[row["object_id"]][row["key"]] = value
        return result

    def _calculate_quantity(
        self,
        obj: dict[str, Any],
        budget: dict[str, Any],
        method: str,
    ) -> dict[str, Any]:
        if method == "count_by_object":
            return {"quantity": 1, "quantity_method": "count_by_object"}
        if method == "length_by_geometry":
            return self._length_from_geometry(obj)
        if method == "area_by_geometry":
            return self._area_from_geometry(obj)
        if method == "manual_review":
            return {
                "quantity": 0,
                "quantity_method": "manual_review",
                "unit": budget.get("unit"),
                "reason": "profile requires manual quantity review",
            }
        return {
            "quantity": 0,
            "quantity_method": "manual_review",
            "unit": budget.get("unit"),
            "reason": f"unsupported quantity method for automatic generation: {method}",
        }

    def _length_from_geometry(self, obj: dict[str, Any]) -> dict[str, Any]:
        raw = self._raw_geometry(obj)
        if raw.get("length") is not None:
            return {
                "quantity": float(raw["length"]),
                "quantity_method": "length_by_geometry",
                "geometry": {"source": "raw_geometry.length", "length": raw["length"]},
            }
        if obj["width"] is not None:
            return {
                "quantity": float(obj["width"]),
                "quantity_method": "length_by_geometry",
                "geometry": {"source": "geometry.width", "width": obj["width"]},
            }
        if obj["height"] is not None:
            return {
                "quantity": float(obj["height"]),
                "quantity_method": "length_by_geometry",
                "geometry": {"source": "geometry.height", "height": obj["height"]},
            }
        return {
            "quantity": 0,
            "quantity_method": "manual_review",
            "reason": "missing length geometry: raw_geometry.length, width, and height are empty",
        }

    def _area_from_geometry(self, obj: dict[str, Any]) -> dict[str, Any]:
        raw = self._raw_geometry(obj)
        if raw.get("area") is not None:
            return {
                "quantity": float(raw["area"]),
                "quantity_method": "area_by_geometry",
                "geometry": {"source": "raw_geometry.area", "area": raw["area"]},
            }
        if obj["width"] is not None and obj["height"] is not None:
            area = float(obj["width"]) * float(obj["height"])
            return {
                "quantity": area,
                "quantity_method": "area_by_geometry",
                "geometry": {
                    "source": "geometry.width_height",
                    "width": obj["width"],
                    "height": obj["height"],
                },
            }
        return {
            "quantity": 0,
            "quantity_method": "manual_review",
            "reason": "missing area geometry: raw_geometry.area or width and height are required",
        }

    @staticmethod
    def _raw_geometry(obj: dict[str, Any]) -> dict[str, Any]:
        if not obj.get("raw_geometry_json"):
            return {}
        return json.loads(obj["raw_geometry_json"])

    @staticmethod
    def _build_group(
        class_code: str,
        group_by: list[str],
        attributes: dict[str, Any],
    ) -> tuple[str, str | None, dict[str, Any]]:
        used = {key: attributes.get(key) for key in group_by}
        if not group_by:
            return class_code, None, used
        parts = [
            f"{key}={_stringify_group_value(used[key]) if used[key] is not None else '<missing>'}"
            for key in group_by
        ]
        return f"{class_code}|" + "|".join(parts), ", ".join(parts), used

    @staticmethod
    def _attribute_value(attributes: dict[str, Any], key: str) -> str | None:
        value = attributes.get(key)
        if value is None:
            return None
        return _stringify_group_value(value)

    @staticmethod
    def _build_evidence(
        obj: dict[str, Any],
        profile: dict[str, Any],
        requested_method: str,
        actual_method: str,
        used_attributes: dict[str, Any],
        geometry: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "source_object_id": obj["id"],
            "class_code": obj["class"],
            "quantity_method": actual_method,
            "requested_quantity_method": requested_method,
            "profile_group": profile.get("profile_group"),
            "used_attributes": used_attributes,
            "generator": "quantity_generator",
            "generator_version": "0.1",
        }
        if geometry:
            evidence["geometry"] = geometry
        if reason:
            evidence["reason"] = reason
        return evidence

    @staticmethod
    def _load_profiles(path: Path) -> dict[str, dict[str, Any]]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {item["code"]: item for item in payload.get("class_profiles", [])}


def _stringify_group_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)
