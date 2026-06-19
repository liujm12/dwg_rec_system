from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .quantity import DEFAULT_PROFILE_PATH


DEFAULT_REQUIRED_RELATION_TYPES = [
    "located_in",
    "belongs_to_system",
    "connected_to",
    "mounted_on",
    "powered_by",
    "controlled_by",
]


class DataQualityChecker:
    def __init__(
        self,
        connection: sqlite3.Connection,
        profile_path: str | Path | None = None,
        low_confidence_threshold: float = 0.8,
        required_relation_types: list[str] | None = None,
    ):
        self.connection = connection
        self.profile_path = Path(profile_path) if profile_path else DEFAULT_PROFILE_PATH
        self.low_confidence_threshold = low_confidence_threshold
        self.required_relation_types = required_relation_types or DEFAULT_REQUIRED_RELATION_TYPES
        self.profiles = self._load_profiles(self.profile_path)

    def check(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> dict[str, Any]:
        objects = self._load_objects(project_id=project_id, drawing_id=drawing_id)
        object_ids = [item["id"] for item in objects]
        attributes = self._load_attributes(object_ids)
        relations = self._load_relation_types(object_ids)
        quantities = self._load_quantities(project_id=project_id, drawing_id=drawing_id)

        findings: list[dict[str, Any]] = []
        for obj in objects:
            findings.extend(self._check_object(obj, attributes.get(obj["id"], {}), relations.get(obj["id"], set())))
        for quantity in quantities:
            findings.extend(self._check_quantity(quantity))

        findings = sorted(
            findings,
            key=lambda item: (
                item["severity"],
                item["category"],
                item.get("class_code") or "",
                item.get("object_id") or "",
                item.get("quantity_item_id") or "",
                item.get("field_name") or "",
                item.get("code") or "",
            ),
        )
        for index, finding in enumerate(findings, start=1):
            finding["finding_id"] = f"dq_{index:05d}"

        return {
            "summary": self._summary(objects, quantities, findings),
            "findings": findings,
        }

    def _check_object(
        self,
        obj: dict[str, Any],
        attributes: dict[str, Any],
        relation_types: set[str],
    ) -> list[dict[str, Any]]:
        class_code = obj["class"]
        profile = self.profiles.get(class_code)
        findings: list[dict[str, Any]] = []

        if float(obj["confidence"] or 0) < self.low_confidence_threshold:
            findings.append(
                self._finding(
                    severity="warning",
                    category="low_confidence",
                    code="LOW_OBJECT_CONFIDENCE",
                    message=(
                        f"{class_code} confidence {obj['confidence']} is below "
                        f"{self.low_confidence_threshold}"
                    ),
                    obj=obj,
                    expected=self.low_confidence_threshold,
                    actual=obj["confidence"],
                    source="cad_object.confidence",
                    evidence={"threshold": self.low_confidence_threshold},
                )
            )

        if not profile:
            findings.append(
                self._finding(
                    severity="info",
                    category="missing_profile",
                    code="MISSING_ENGINEERING_PROFILE",
                    message=f"{class_code} has no engineering class profile",
                    obj=obj,
                    expected="engineering_class_profiles.json entry",
                    actual=None,
                    source="engineering_class_profiles",
                    evidence={"class_code": class_code},
                )
            )
            return findings

        group_by = set((profile.get("budget") or {}).get("group_by") or [])
        for field_name in profile.get("expected_attributes") or []:
            value = attributes.get(field_name)
            if self._is_missing(value):
                is_group_field = field_name in group_by
                findings.append(
                    self._finding(
                        severity="error" if is_group_field else "warning",
                        category="missing_attribute",
                        code="MISSING_GROUP_ATTRIBUTE" if is_group_field else "MISSING_EXPECTED_ATTRIBUTE",
                        message=f"{class_code} is missing expected attribute {field_name}",
                        obj=obj,
                        profile=profile,
                        field_name=field_name,
                        expected=field_name,
                        actual=value,
                        source="engineering_class_profiles.expected_attributes",
                        evidence={
                            "profile_code": class_code,
                            "profile_group": profile.get("profile_group"),
                            "is_budget_group_by": is_group_field,
                        },
                    )
                )

        budget = profile.get("budget") or {}
        method = budget.get("quantity_method")
        geometry_finding = self._geometry_finding(obj, profile, method)
        if geometry_finding:
            findings.append(geometry_finding)

        required_profile_relations = set(profile.get("relations") or []) & set(self.required_relation_types)
        for relation_type in sorted(required_profile_relations):
            if relation_type not in relation_types:
                findings.append(
                    self._finding(
                        severity="warning",
                        category="missing_relation",
                        code="MISSING_ACCEPTED_RELATION",
                        message=f"{class_code} has no accepted {relation_type} relation",
                        obj=obj,
                        profile=profile,
                        field_name=relation_type,
                        expected=relation_type,
                        actual=None,
                        source="relation",
                        evidence={
                            "required_relation_type": relation_type,
                            "required_relation_types": self.required_relation_types,
                        },
                    )
                )

        return findings

    def _geometry_finding(
        self,
        obj: dict[str, Any],
        profile: dict[str, Any],
        method: str | None,
    ) -> dict[str, Any] | None:
        raw = self._raw_geometry(obj)
        if method == "length_by_geometry":
            if raw.get("length") is not None or obj["width"] is not None or obj["height"] is not None:
                return None
            return self._finding(
                severity="error",
                category="missing_geometry",
                code="MISSING_LENGTH_GEOMETRY",
                message=f"{obj['class']} is missing geometry for length quantity",
                obj=obj,
                profile=profile,
                field_name="length",
                expected=["raw_geometry.length", "geometry.width", "geometry.height"],
                actual={
                    "raw_geometry.length": raw.get("length"),
                    "geometry.width": obj["width"],
                    "geometry.height": obj["height"],
                },
                source="geometry",
                evidence={"quantity_method": method},
            )
        if method == "area_by_geometry":
            has_raw_area = raw.get("area") is not None
            has_width_height = obj["width"] is not None and obj["height"] is not None
            if has_raw_area or has_width_height:
                return None
            return self._finding(
                severity="error",
                category="missing_geometry",
                code="MISSING_AREA_GEOMETRY",
                message=f"{obj['class']} is missing geometry for area quantity",
                obj=obj,
                profile=profile,
                field_name="area",
                expected=["raw_geometry.area", "geometry.width + geometry.height"],
                actual={
                    "raw_geometry.area": raw.get("area"),
                    "geometry.width": obj["width"],
                    "geometry.height": obj["height"],
                },
                source="geometry",
                evidence={"quantity_method": method},
            )
        return None

    def _check_quantity(self, quantity: dict[str, Any]) -> list[dict[str, Any]]:
        if quantity["quantity_method"] != "manual_review":
            return []
        evidence = self._parse_json(quantity.get("evidence_json"))
        return [
            self._finding(
                severity="error",
                category="manual_review_quantity",
                code="MANUAL_REVIEW_QUANTITY",
                message=f"{quantity['class_code']} quantity requires manual review",
                project_id=quantity["project_id"],
                drawing_id=quantity["drawing_id"],
                object_id=quantity["source_object_id"],
                quantity_item_id=quantity["id"],
                class_code=quantity["class_code"],
                discipline=quantity["discipline"],
                field_name="quantity_method",
                expected="automatic quantity method",
                actual="manual_review",
                source="quantity_item",
                evidence=evidence,
            )
        ]

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
        rows = self.connection.execute(
            f"""
            SELECT
                o.id,
                o.drawing_id,
                d.project_id,
                o.class,
                o.confidence,
                oc.discipline,
                g.width,
                g.height,
                g.raw_geometry_json
            FROM cad_object o
            LEFT JOIN drawing d ON d.id = o.drawing_id
            LEFT JOIN object_class oc ON oc.id = o.class_id
            LEFT JOIN geometry g ON g.object_id = o.id
            WHERE {' AND '.join(conditions)}
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

    def _load_relation_types(self, object_ids: list[str]) -> dict[str, set[str]]:
        result: dict[str, set[str]] = defaultdict(set)
        if not object_ids:
            return result
        placeholders = ",".join("?" for _ in object_ids)
        rows = self.connection.execute(
            f"""
            SELECT source_id, target_id, relation_type
            FROM relation
            WHERE status = 'active'
              AND (source_id IN ({placeholders}) OR target_id IN ({placeholders}))
            """,
            object_ids + object_ids,
        ).fetchall()
        for row in rows:
            result[row["source_id"]].add(row["relation_type"])
            result[row["target_id"]].add(row["relation_type"])
        return result

    def _load_quantities(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if drawing_id:
            conditions.append("drawing_id = ?")
            params.append(drawing_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM quantity_item
            {where}
            ORDER BY class_code, source_object_id, id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def _finding(
        self,
        severity: str,
        category: str,
        code: str,
        message: str,
        source: str,
        obj: dict[str, Any] | None = None,
        profile: dict[str, Any] | None = None,
        project_id: str | None = None,
        drawing_id: str | None = None,
        object_id: str | None = None,
        quantity_item_id: str | None = None,
        class_code: str | None = None,
        discipline: str | None = None,
        field_name: str | None = None,
        expected: Any = None,
        actual: Any = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "finding_id": None,
            "severity": severity,
            "category": category,
            "code": code,
            "message": message,
            "project_id": project_id if project_id is not None else (obj or {}).get("project_id"),
            "drawing_id": drawing_id if drawing_id is not None else (obj or {}).get("drawing_id"),
            "object_id": object_id if object_id is not None else (obj or {}).get("id"),
            "quantity_item_id": quantity_item_id,
            "class_code": class_code if class_code is not None else (obj or {}).get("class"),
            "discipline": discipline if discipline is not None else (obj or {}).get("discipline"),
            "profile_group": (profile or {}).get("profile_group"),
            "field_name": field_name,
            "expected": expected,
            "actual": actual,
            "source": source,
            "evidence": evidence or {},
            "status": "open",
        }

    @staticmethod
    def _summary(
        objects: list[dict[str, Any]],
        quantities: list[dict[str, Any]],
        findings: list[dict[str, Any]],
    ) -> dict[str, Any]:
        by_severity = Counter(item["severity"] for item in findings)
        by_category = Counter(item["category"] for item in findings)
        return {
            "objects_checked": len(objects),
            "quantities_checked": len(quantities),
            "findings_total": len(findings),
            "by_severity": {
                "error": by_severity.get("error", 0),
                "warning": by_severity.get("warning", 0),
                "info": by_severity.get("info", 0),
            },
            "by_category": dict(sorted(by_category.items())),
        }

    @staticmethod
    def _raw_geometry(obj: dict[str, Any]) -> dict[str, Any]:
        if not obj.get("raw_geometry_json"):
            return {}
        return json.loads(obj["raw_geometry_json"])

    @staticmethod
    def _parse_json(value: str | None) -> Any:
        if not value:
            return {}
        return json.loads(value)

    @staticmethod
    def _is_missing(value: Any) -> bool:
        return value is None or value == "" or value == []

    @staticmethod
    def _load_profiles(path: Path) -> dict[str, dict[str, Any]]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {item["code"]: item for item in payload.get("class_profiles", [])}


def filter_findings(
    findings: list[dict[str, Any]],
    severity: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    return [
        item
        for item in findings
        if (severity is None or item["severity"] == severity)
        and (category is None or item["category"] == category)
    ]
