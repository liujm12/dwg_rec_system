from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any, Iterable

from .models import CadMetaInput, GeometryInput, RuleTemplateInput


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def _json_or_none(value: dict[str, Any] | list[Any] | None) -> str | None:
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if value is not None else None


class DrawingRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def create(
        self,
        drawing_no: str,
        revision: str | None = None,
        discipline: str | None = None,
        sheet: str | None = None,
        title: str | None = None,
        source_file: str | None = None,
        project_id: str | None = None,
    ) -> str:
        drawing_id = new_id("drw")
        self.connection.execute(
            """
            INSERT INTO drawing(id, project_id, drawing_no, revision, discipline, sheet, title, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (drawing_id, project_id, drawing_no, revision, discipline, sheet, title, source_file),
        )
        return drawing_id

    def get_or_create(
        self,
        drawing_no: str,
        revision: str | None = None,
        discipline: str | None = None,
        sheet: str | None = None,
        title: str | None = None,
        source_file: str | None = None,
        project_id: str | None = None,
    ) -> str:
        existing = self.connection.execute(
            """
            SELECT id FROM drawing
            WHERE drawing_no = ?
              AND COALESCE(revision, '') = COALESCE(?, '')
              AND COALESCE(sheet, '') = COALESCE(?, '')
            """,
            (drawing_no, revision, sheet),
        ).fetchone()
        if existing:
            return existing["id"]
        return self.create(drawing_no, revision, discipline, sheet, title, source_file, project_id)


class ProjectRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get_or_create(
        self,
        code: str,
        name: str,
        owner: str | None = None,
        description: str | None = None,
    ) -> str:
        existing = self.connection.execute(
            "SELECT id FROM project WHERE code = ?",
            (code,),
        ).fetchone()
        if existing:
            return existing["id"]
        project_id = new_id("prj")
        self.connection.execute(
            """
            INSERT INTO project(id, code, name, owner, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, code, name, owner, description),
        )
        return project_id


class ObjectClassRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def find_by_code(self, code: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM object_class WHERE code = ?",
            (code,),
        ).fetchone()
        return row_to_dict(row)

    def get_or_create(
        self,
        code: str,
        name: str | None = None,
        parent_code: str | None = None,
        discipline: str | None = None,
        description: str | None = None,
    ) -> str:
        existing = self.connection.execute(
            "SELECT id FROM object_class WHERE code = ?",
            (code,),
        ).fetchone()
        if existing:
            return existing["id"]
        class_id = new_id("cls")
        self.connection.execute(
            """
            INSERT INTO object_class(id, code, name, parent_code, discipline, description)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (class_id, code, name or code, parent_code, discipline, description),
        )
        return class_id


class ObjectRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def create(
        self,
        class_name: str,
        subtype: str | None = None,
        source_file: str | None = None,
        handle: str | None = None,
        drawing_id: str | None = None,
        import_job_id: str | None = None,
        class_id: str | None = None,
        confidence: float = 1.0,
        status: str = "auto",
        parser_name: str | None = None,
        parser_version: str | None = None,
        recognition_model: str | None = None,
        recognition_version: str | None = None,
    ) -> str:
        object_id = new_id("obj")
        self.connection.execute(
            """
            INSERT INTO cad_object(
                id, drawing_id, import_job_id, class_id, source_file, handle,
                class, subtype, confidence, status,
                parser_name, parser_version, recognition_model, recognition_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                object_id,
                drawing_id,
                import_job_id,
                class_id,
                source_file,
                handle,
                class_name,
                subtype,
                confidence,
                status,
                parser_name,
                parser_version,
                recognition_model,
                recognition_version,
            ),
        )
        return object_id

    def find_by_source_handle(self, source_file: str | None, handle: str | None) -> str | None:
        if not source_file or not handle:
            return None
        row = self.connection.execute(
            "SELECT id FROM cad_object WHERE source_file = ? AND handle = ?",
            (source_file, handle),
        ).fetchone()
        return row["id"] if row else None

    def list(self, class_name: str | None = None) -> list[dict[str, Any]]:
        if class_name:
            rows = self.connection.execute(
                "SELECT * FROM cad_object WHERE class = ? ORDER BY created_at, id",
                (class_name,),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM cad_object ORDER BY created_at, id"
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, object_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM cad_object WHERE id = ?",
            (object_id,),
        ).fetchone()
        return row_to_dict(row)


class GeometryRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def upsert(self, object_id: str, geometry: GeometryInput) -> None:
        min_x, min_y, max_x, max_y = self._bounds(geometry)
        bbox = None
        if min_x is not None and min_y is not None and max_x is not None and max_y is not None:
            bbox = {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y}
        self.connection.execute(
            """
            INSERT INTO geometry(
                object_id, center_x, center_y, width, height, rotation,
                min_x, min_y, max_x, max_y, bbox_json,
                geometry_type, geometry_wkt, geometry_srid, raw_geometry_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(object_id) DO UPDATE SET
                center_x = excluded.center_x,
                center_y = excluded.center_y,
                width = excluded.width,
                height = excluded.height,
                rotation = excluded.rotation,
                min_x = excluded.min_x,
                min_y = excluded.min_y,
                max_x = excluded.max_x,
                max_y = excluded.max_y,
                bbox_json = excluded.bbox_json,
                geometry_type = excluded.geometry_type,
                geometry_wkt = excluded.geometry_wkt,
                geometry_srid = excluded.geometry_srid,
                raw_geometry_json = excluded.raw_geometry_json,
                updated_at = datetime('now')
            """,
            (
                object_id,
                geometry.center_x,
                geometry.center_y,
                geometry.width,
                geometry.height,
                geometry.rotation,
                min_x,
                min_y,
                max_x,
                max_y,
                json.dumps(bbox, ensure_ascii=False) if bbox else None,
                geometry.geometry_type,
                geometry.geometry_wkt,
                geometry.geometry_srid,
                json.dumps(geometry.raw_geometry, ensure_ascii=False) if geometry.raw_geometry else None,
            ),
        )
        self._sync_spatial_index(object_id, min_x, min_y, max_x, max_y)

    def _sync_spatial_index(
        self,
        object_id: str,
        min_x: float | None,
        min_y: float | None,
        max_x: float | None,
        max_y: float | None,
    ) -> None:
        if None in (min_x, min_y, max_x, max_y):
            row = self.connection.execute(
                "SELECT rowid FROM geometry_rtree_map WHERE object_id = ?",
                (object_id,),
            ).fetchone()
            if row:
                self.connection.execute("DELETE FROM geometry_rtree WHERE rowid = ?", (row["rowid"],))
                self.connection.execute("DELETE FROM geometry_rtree_map WHERE rowid = ?", (row["rowid"],))
            return

        self.connection.execute(
            "INSERT OR IGNORE INTO geometry_rtree_map(object_id) VALUES (?)",
            (object_id,),
        )
        row = self.connection.execute(
            "SELECT rowid FROM geometry_rtree_map WHERE object_id = ?",
            (object_id,),
        ).fetchone()
        self.connection.execute(
            """
            INSERT OR REPLACE INTO geometry_rtree(rowid, min_x, max_x, min_y, max_y)
            VALUES (?, ?, ?, ?, ?)
            """,
            (row["rowid"], min_x, max_x, min_y, max_y),
        )

    @staticmethod
    def _bounds(geometry: GeometryInput) -> tuple[float | None, float | None, float | None, float | None]:
        if None not in (geometry.min_x, geometry.min_y, geometry.max_x, geometry.max_y):
            return geometry.min_x, geometry.min_y, geometry.max_x, geometry.max_y
        if None in (geometry.center_x, geometry.center_y, geometry.width, geometry.height):
            return None, None, None, None
        half_w = geometry.width / 2
        half_h = geometry.height / 2
        return (
            geometry.center_x - half_w,
            geometry.center_y - half_h,
            geometry.center_x + half_w,
            geometry.center_y + half_h,
        )


class CadMetaRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def upsert(self, object_id: str, meta: CadMetaInput) -> None:
        self.connection.execute(
            """
            INSERT INTO cad_meta(object_id, layer, block_name, color, linetype, owner_block, raw_meta_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(object_id) DO UPDATE SET
                layer = excluded.layer,
                block_name = excluded.block_name,
                color = excluded.color,
                linetype = excluded.linetype,
                owner_block = excluded.owner_block,
                raw_meta_json = excluded.raw_meta_json,
                updated_at = datetime('now')
            """,
            (
                object_id,
                meta.layer,
                meta.block_name,
                meta.color,
                meta.linetype,
                meta.owner_block,
                json.dumps(meta.raw_meta, ensure_ascii=False) if meta.raw_meta else None,
            ),
        )


class AttributeRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def set(
        self,
        object_id: str,
        key: str,
        value: Any,
        source: str = "auto",
        confidence: float = 1.0,
        namespace: str = "default",
        normalized_value: str | None = None,
        unit: str | None = None,
        is_inferred: bool = False,
    ) -> None:
        attribute_id = new_id("att")
        value_type = type(value).__name__
        if isinstance(value, (dict, list)):
            stored_value = json.dumps(value, ensure_ascii=False)
            value_type = "json"
        elif value is None:
            stored_value = None
            value_type = "null"
        else:
            stored_value = str(value)
        self.connection.execute(
            """
            INSERT INTO attribute(
                id, object_id, namespace, key, value, normalized_value,
                unit, value_type, is_inferred, confidence, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT DO UPDATE SET
                value = excluded.value,
                normalized_value = excluded.normalized_value,
                unit = excluded.unit,
                value_type = excluded.value_type,
                is_inferred = excluded.is_inferred,
                confidence = excluded.confidence,
                source = excluded.source,
                updated_at = datetime('now')
            """,
            (
                attribute_id,
                object_id,
                namespace,
                key,
                stored_value,
                normalized_value,
                unit,
                value_type,
                1 if is_inferred else 0,
                confidence,
                source,
            ),
        )

    def bulk_set(self, object_id: str, attributes: dict[str, Any], source: str = "auto") -> None:
        for key, value in attributes.items():
            self.set(object_id, key, value, source=source)


class RelationRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def upsert(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        confidence: float,
        source: str = "auto",
        rule_id: str | None = None,
        candidate_id: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> str:
        relation_id = new_id("rel")
        self.connection.execute(
            """
            INSERT INTO relation(
                id, source_id, target_id, relation_type, confidence,
                source, rule_id, candidate_id, evidence_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, target_id, relation_type) DO UPDATE SET
                confidence = excluded.confidence,
                source = excluded.source,
                rule_id = excluded.rule_id,
                candidate_id = excluded.candidate_id,
                evidence_json = excluded.evidence_json,
                status = 'active',
                updated_at = datetime('now')
            """,
            (
                relation_id,
                source_id,
                target_id,
                relation_type,
                confidence,
                source,
                rule_id,
                candidate_id,
                json.dumps(evidence, ensure_ascii=False) if evidence else None,
            ),
        )
        row = self.connection.execute(
            """
            SELECT id FROM relation
            WHERE source_id = ? AND target_id = ? AND relation_type = ?
            """,
            (source_id, target_id, relation_type),
        ).fetchone()
        return row["id"]

    def list(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM relation ORDER BY relation_type, confidence DESC, id"
        ).fetchall()
        return [dict(row) for row in rows]


class RelationCandidateRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def list(
        self,
        status: str | None = None,
        source: str | None = None,
        relation_type: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if source:
            conditions.append("source = ?")
            params.append(source)
        if relation_type:
            conditions.append("relation_type = ?")
            params.append(relation_type)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM relation_candidate
            {where}
            ORDER BY created_at, id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, candidate_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM relation_candidate WHERE id = ?",
            (candidate_id,),
        ).fetchone()
        return row_to_dict(row)

    def upsert(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        confidence: float,
        source: str,
        rule_id: str | None = None,
        inference_job_id: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> str:
        candidate_id = new_id("rcd")
        self.connection.execute(
            """
            INSERT INTO relation_candidate(
                id, source_id, target_id, relation_type, confidence,
                source, rule_id, inference_job_id, evidence_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, target_id, relation_type, source) DO UPDATE SET
                confidence = excluded.confidence,
                rule_id = excluded.rule_id,
                inference_job_id = excluded.inference_job_id,
                evidence_json = excluded.evidence_json,
                status = 'pending',
                updated_at = datetime('now')
            """,
            (
                candidate_id,
                source_id,
                target_id,
                relation_type,
                confidence,
                source,
                rule_id,
                inference_job_id,
                json.dumps(evidence, ensure_ascii=False) if evidence else None,
            ),
        )
        row = self.connection.execute(
            """
            SELECT id FROM relation_candidate
            WHERE source_id = ? AND target_id = ? AND relation_type = ? AND source = ?
            """,
            (source_id, target_id, relation_type, source),
        ).fetchone()
        return row["id"]

    def accept(self, candidate_id: str) -> str:
        candidate = self.connection.execute(
            "SELECT * FROM relation_candidate WHERE id = ?",
            (candidate_id,),
        ).fetchone()
        if not candidate:
            raise ValueError(f"relation candidate not found: {candidate_id}")
        relation_id = RelationRepository(self.connection).upsert(
            source_id=candidate["source_id"],
            target_id=candidate["target_id"],
            relation_type=candidate["relation_type"],
            confidence=candidate["confidence"],
            source=candidate["source"],
            rule_id=candidate["rule_id"],
            candidate_id=candidate_id,
            evidence=json.loads(candidate["evidence_json"]) if candidate["evidence_json"] else None,
        )
        self.connection.execute(
            "UPDATE relation_candidate SET status = 'accepted', updated_at = datetime('now') WHERE id = ?",
            (candidate_id,),
        )
        return relation_id

    def reject(self, candidate_id: str) -> None:
        cursor = self.connection.execute(
            """
            UPDATE relation_candidate
            SET status = 'rejected', updated_at = datetime('now')
            WHERE id = ?
            """,
            (candidate_id,),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"relation candidate not found: {candidate_id}")


class QuantityRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def upsert(
        self,
        class_code: str,
        item_name: str,
        unit: str,
        quantity: float,
        quantity_method: str,
        project_id: str | None = None,
        drawing_id: str | None = None,
        source_object_id: str | None = None,
        discipline: str | None = None,
        spec: str | None = None,
        group_key: str | None = None,
        location: str | None = None,
        system_code: str | None = None,
        confidence: float = 1.0,
        source: str = "auto",
        evidence: dict[str, Any] | None = None,
        status: str = "auto",
    ) -> str:
        quantity_id = new_id("qty")
        self.connection.execute(
            """
            INSERT INTO quantity_item(
                id, project_id, drawing_id, source_object_id, class_code,
                discipline, item_name, spec, unit, quantity, quantity_method,
                group_key, location, system_code, confidence, source,
                evidence_json, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                quantity_id,
                project_id,
                drawing_id,
                source_object_id,
                class_code,
                discipline,
                item_name,
                spec,
                unit,
                quantity,
                quantity_method,
                group_key,
                location,
                system_code,
                confidence,
                source,
                json.dumps(evidence, ensure_ascii=False) if evidence else None,
                status,
            ),
        )
        return quantity_id

    def clear_auto(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> int:
        conditions = ["source = 'auto'", "status = 'auto'"]
        params: list[Any] = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if drawing_id:
            conditions.append("drawing_id = ?")
            params.append(drawing_id)
        cursor = self.connection.execute(
            f"DELETE FROM quantity_item WHERE {' AND '.join(conditions)}",
            params,
        )
        return cursor.rowcount

    def list(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
        class_code: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if drawing_id:
            conditions.append("drawing_id = ?")
            params.append(drawing_id)
        if class_code:
            conditions.append("class_code = ?")
            params.append(class_code)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM quantity_item
            {where}
            ORDER BY class_code, group_key, source_object_id, id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


class CostItemRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def upsert(
        self,
        code: str,
        name: str,
        class_code: str,
        unit: str,
        discipline: str | None = None,
        spec_pattern: str | None = None,
        unit_price_material: float = 0,
        unit_price_labor: float = 0,
        unit_price_machine: float = 0,
        currency: str = "CNY",
        region: str | None = None,
        version: str | None = None,
        effective_from: str | None = None,
        effective_to: str | None = None,
        description: str | None = None,
        status: str = "active",
    ) -> str:
        cost_id = new_id("cost")
        self.connection.execute(
            """
            INSERT INTO cost_item(
                id, code, name, discipline, class_code, spec_pattern, unit,
                unit_price_material, unit_price_labor, unit_price_machine,
                currency, region, version, effective_from, effective_to,
                description, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                name = excluded.name,
                discipline = excluded.discipline,
                class_code = excluded.class_code,
                spec_pattern = excluded.spec_pattern,
                unit = excluded.unit,
                unit_price_material = excluded.unit_price_material,
                unit_price_labor = excluded.unit_price_labor,
                unit_price_machine = excluded.unit_price_machine,
                currency = excluded.currency,
                region = excluded.region,
                version = excluded.version,
                effective_from = excluded.effective_from,
                effective_to = excluded.effective_to,
                description = excluded.description,
                status = excluded.status,
                updated_at = datetime('now')
            """,
            (
                cost_id,
                code,
                name,
                discipline,
                class_code,
                spec_pattern,
                unit,
                unit_price_material,
                unit_price_labor,
                unit_price_machine,
                currency,
                region,
                version,
                effective_from,
                effective_to,
                description,
                status,
            ),
        )
        row = self.connection.execute(
            "SELECT id FROM cost_item WHERE code = ?",
            (code,),
        ).fetchone()
        return row["id"]

    def list(
        self,
        class_code: str | None = None,
        discipline: str | None = None,
        unit: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if class_code:
            conditions.append("class_code = ?")
            params.append(class_code)
        if discipline:
            conditions.append("discipline = ?")
            params.append(discipline)
        if unit:
            conditions.append("unit = ?")
            params.append(unit)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM cost_item
            {where}
            ORDER BY class_code, unit, code
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def find_matches(self, class_code: str, unit: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM cost_item
            WHERE class_code = ?
              AND unit = ?
              AND status = 'active'
            ORDER BY code
            """,
            (class_code, unit),
        ).fetchall()
        return [dict(row) for row in rows]


class BudgetItemRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def create(
        self,
        item_name: str,
        unit: str,
        quantity: float,
        project_id: str | None = None,
        drawing_id: str | None = None,
        quantity_item_id: str | None = None,
        cost_item_id: str | None = None,
        class_code: str | None = None,
        discipline: str | None = None,
        spec: str | None = None,
        unit_price_material: float = 0,
        unit_price_labor: float = 0,
        unit_price_machine: float = 0,
        material_cost: float = 0,
        labor_cost: float = 0,
        machine_cost: float = 0,
        total_cost: float = 0,
        pricing_source: str = "auto",
        confidence: float = 1.0,
        evidence: dict[str, Any] | None = None,
        status: str = "auto",
    ) -> str:
        budget_id = new_id("bud")
        self.connection.execute(
            """
            INSERT INTO budget_item(
                id, project_id, drawing_id, quantity_item_id, cost_item_id,
                class_code, discipline, item_name, spec, unit, quantity,
                unit_price_material, unit_price_labor, unit_price_machine,
                material_cost, labor_cost, machine_cost, total_cost,
                pricing_source, confidence, evidence_json, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                budget_id,
                project_id,
                drawing_id,
                quantity_item_id,
                cost_item_id,
                class_code,
                discipline,
                item_name,
                spec,
                unit,
                quantity,
                unit_price_material,
                unit_price_labor,
                unit_price_machine,
                material_cost,
                labor_cost,
                machine_cost,
                total_cost,
                pricing_source,
                confidence,
                json.dumps(evidence, ensure_ascii=False) if evidence else None,
                status,
            ),
        )
        return budget_id

    def clear_auto(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> int:
        conditions = ["status IN ('auto', 'matched', 'unmatched', 'review')"]
        params: list[Any] = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if drawing_id:
            conditions.append("drawing_id = ?")
            params.append(drawing_id)
        cursor = self.connection.execute(
            f"DELETE FROM budget_item WHERE {' AND '.join(conditions)}",
            params,
        )
        return cursor.rowcount

    def list(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
        class_code: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if drawing_id:
            conditions.append("drawing_id = ?")
            params.append(drawing_id)
        if class_code:
            conditions.append("class_code = ?")
            params.append(class_code)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM budget_item
            {where}
            ORDER BY class_code, status, item_name, id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


class InstallTaskRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def create(
        self,
        class_code: str,
        task_name: str,
        project_id: str | None = None,
        drawing_id: str | None = None,
        object_id: str | None = None,
        discipline: str | None = None,
        work_package: str | None = None,
        location: str | None = None,
        system_code: str | None = None,
        priority: int = 100,
        estimated_duration: float | None = None,
        crew_type: str | None = None,
        source: str = "auto",
        confidence: float = 1.0,
        evidence: dict[str, Any] | None = None,
        status: str = "auto",
    ) -> str:
        task_id = new_id("itask")
        self.connection.execute(
            """
            INSERT INTO install_task(
                id, project_id, drawing_id, object_id, class_code, discipline,
                task_name, work_package, location, system_code, priority,
                estimated_duration, crew_type, source, confidence, evidence_json, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                project_id,
                drawing_id,
                object_id,
                class_code,
                discipline,
                task_name,
                work_package,
                location,
                system_code,
                priority,
                estimated_duration,
                crew_type,
                source,
                confidence,
                json.dumps(evidence, ensure_ascii=False) if evidence else None,
                status,
            ),
        )
        return task_id

    def clear_auto(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> int:
        conditions = ["source = 'auto'", "status IN ('auto', 'review', 'ready', 'blocked')"]
        params: list[Any] = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if drawing_id:
            conditions.append("drawing_id = ?")
            params.append(drawing_id)
        cursor = self.connection.execute(
            f"DELETE FROM install_task WHERE {' AND '.join(conditions)}",
            params,
        )
        return cursor.rowcount

    def list(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
        class_code: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if drawing_id:
            conditions.append("drawing_id = ?")
            params.append(drawing_id)
        if class_code:
            conditions.append("class_code = ?")
            params.append(class_code)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM install_task
            {where}
            ORDER BY work_package, class_code, task_name, id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


class InstallDependencyRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def create(
        self,
        predecessor_task_id: str,
        successor_task_id: str,
        dependency_type: str,
        reason: str | None = None,
        source: str = "auto",
        confidence: float = 1.0,
        evidence: dict[str, Any] | None = None,
        status: str = "auto",
    ) -> str:
        dependency_id = new_id("idep")
        self.connection.execute(
            """
            INSERT INTO install_dependency(
                id, predecessor_task_id, successor_task_id, dependency_type,
                reason, source, confidence, evidence_json, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dependency_id,
                predecessor_task_id,
                successor_task_id,
                dependency_type,
                reason,
                source,
                confidence,
                json.dumps(evidence, ensure_ascii=False) if evidence else None,
                status,
            ),
        )
        return dependency_id

    def clear_auto(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> int:
        conditions = ["source = 'auto'", "status IN ('auto', 'review')"]
        params: list[Any] = []
        if project_id or drawing_id:
            task_conditions: list[str] = []
            if project_id:
                task_conditions.append("project_id = ?")
                params.append(project_id)
            if drawing_id:
                task_conditions.append("drawing_id = ?")
                params.append(drawing_id)
            task_where = " AND ".join(task_conditions)
            conditions.append(
                f"""
                (
                    predecessor_task_id IN (SELECT id FROM install_task WHERE {task_where})
                    OR successor_task_id IN (SELECT id FROM install_task WHERE {task_where})
                )
                """
            )
            params.extend(params.copy())
        cursor = self.connection.execute(
            f"DELETE FROM install_dependency WHERE {' AND '.join(conditions)}",
            params,
        )
        return cursor.rowcount

    def list(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if project_id:
            conditions.append("(pt.project_id = ? OR st.project_id = ?)")
            params.extend([project_id, project_id])
        if drawing_id:
            conditions.append("(pt.drawing_id = ? OR st.drawing_id = ?)")
            params.extend([drawing_id, drawing_id])
        if status:
            conditions.append("d.status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"""
            SELECT d.*
            FROM install_dependency d
            LEFT JOIN install_task pt ON pt.id = d.predecessor_task_id
            LEFT JOIN install_task st ON st.id = d.successor_task_id
            {where}
            ORDER BY d.status, d.dependency_type, d.id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


class InstallInstructionRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def create(
        self,
        task_id: str,
        instruction_text: str,
        generator: str = "template",
        generator_version: str = "0.1",
        source: dict[str, Any] | None = None,
    ) -> str:
        instruction_id = new_id("iins")
        self.connection.execute(
            """
            INSERT INTO install_instruction(
                id, task_id, instruction_text, generator, generator_version, source_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                instruction_id,
                task_id,
                instruction_text,
                generator,
                generator_version,
                json.dumps(source, ensure_ascii=False) if source else None,
            ),
        )
        return instruction_id

    def clear_auto(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> int:
        conditions = ["generator = 'template'"]
        params: list[Any] = []
        if project_id or drawing_id:
            task_conditions: list[str] = []
            if project_id:
                task_conditions.append("project_id = ?")
                params.append(project_id)
            if drawing_id:
                task_conditions.append("drawing_id = ?")
                params.append(drawing_id)
            conditions.append(
                f"task_id IN (SELECT id FROM install_task WHERE {' AND '.join(task_conditions)})"
            )
        cursor = self.connection.execute(
            f"DELETE FROM install_instruction WHERE {' AND '.join(conditions)}",
            params,
        )
        return cursor.rowcount

    def list(
        self,
        task_id: str | None = None,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if task_id:
            conditions.append("i.task_id = ?")
            params.append(task_id)
        if project_id:
            conditions.append("t.project_id = ?")
            params.append(project_id)
        if drawing_id:
            conditions.append("t.drawing_id = ?")
            params.append(drawing_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"""
            SELECT i.*
            FROM install_instruction i
            LEFT JOIN install_task t ON t.id = i.task_id
            {where}
            ORDER BY t.work_package, t.class_code, i.created_at, i.id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


class WorkflowPlanRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def create(
        self,
        name: str,
        project_id: str | None = None,
        drawing_id: str | None = None,
        scope: dict[str, Any] | None = None,
        generator: str = "workflow_plan_generator",
        generator_version: str = "0.1",
        status: str = "review",
        summary: dict[str, Any] | None = None,
    ) -> str:
        plan_id = new_id("wplan")
        self.connection.execute(
            """
            INSERT INTO workflow_plan(
                id, project_id, drawing_id, name, scope_json, generator,
                generator_version, status, summary_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                project_id,
                drawing_id,
                name,
                json.dumps(scope, ensure_ascii=False, sort_keys=True) if scope else None,
                generator,
                generator_version,
                status,
                json.dumps(summary, ensure_ascii=False, sort_keys=True) if summary else None,
            ),
        )
        return plan_id

    def mark_superseded(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
        scope: dict[str, Any] | None = None,
    ) -> int:
        conditions = [
            "generator = 'workflow_plan_generator'",
            "status IN ('draft', 'review', 'ready')",
        ]
        params: list[Any] = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        else:
            conditions.append("project_id IS NULL")
        if drawing_id:
            conditions.append("drawing_id = ?")
            params.append(drawing_id)
        else:
            conditions.append("drawing_id IS NULL")
        if scope is not None:
            conditions.append("scope_json = ?")
            params.append(json.dumps(scope, ensure_ascii=False, sort_keys=True))
        cursor = self.connection.execute(
            f"""
            UPDATE workflow_plan
            SET status = 'superseded', updated_at = datetime('now')
            WHERE {' AND '.join(conditions)}
            """,
            params,
        )
        return cursor.rowcount

    def update_summary(self, plan_id: str, summary: dict[str, Any], status: str) -> None:
        self.connection.execute(
            """
            UPDATE workflow_plan
            SET summary_json = ?, status = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (json.dumps(summary, ensure_ascii=False, sort_keys=True), status, plan_id),
        )

    def list(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if drawing_id:
            conditions.append("drawing_id = ?")
            params.append(drawing_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM workflow_plan
            {where}
            ORDER BY created_at DESC, id DESC
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


class WorkflowStepRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def create(
        self,
        plan_id: str,
        task_id: str,
        sequence_no: int,
        sequence_group: str | None = None,
        discipline: str | None = None,
        work_package: str | None = None,
        location: str | None = None,
        system_code: str | None = None,
        dependency_count: int = 0,
        blocked_by_count: int = 0,
        status: str = "planned",
        evidence: dict[str, Any] | None = None,
    ) -> str:
        step_id = new_id("wstep")
        self.connection.execute(
            """
            INSERT INTO workflow_step(
                id, plan_id, task_id, sequence_no, sequence_group, discipline,
                work_package, location, system_code, dependency_count,
                blocked_by_count, status, evidence_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                step_id,
                plan_id,
                task_id,
                sequence_no,
                sequence_group,
                discipline,
                work_package,
                location,
                system_code,
                dependency_count,
                blocked_by_count,
                status,
                json.dumps(evidence, ensure_ascii=False, sort_keys=True) if evidence else None,
            ),
        )
        return step_id

    def clear_for_plan(self, plan_id: str) -> int:
        cursor = self.connection.execute(
            "DELETE FROM workflow_step WHERE plan_id = ?",
            (plan_id,),
        )
        return cursor.rowcount

    def list(
        self,
        plan_id: str | None = None,
        task_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if plan_id:
            conditions.append("s.plan_id = ?")
            params.append(plan_id)
        if task_id:
            conditions.append("s.task_id = ?")
            params.append(task_id)
        if status:
            conditions.append("s.status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"""
            SELECT
                s.*,
                t.task_name,
                t.class_code,
                t.confidence AS task_confidence
            FROM workflow_step s
            LEFT JOIN install_task t ON t.id = s.task_id
            {where}
            ORDER BY s.plan_id, s.sequence_no, s.id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


class WorkflowIssueRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def create(
        self,
        plan_id: str,
        severity: str,
        category: str,
        code: str,
        message: str,
        task_id: str | None = None,
        dependency_id: str | None = None,
        evidence: dict[str, Any] | None = None,
        status: str = "open",
    ) -> str:
        issue_id = new_id("wiss")
        self.connection.execute(
            """
            INSERT INTO workflow_issue(
                id, plan_id, task_id, dependency_id, severity, category,
                code, message, evidence_json, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                issue_id,
                plan_id,
                task_id,
                dependency_id,
                severity,
                category,
                code,
                message,
                json.dumps(evidence, ensure_ascii=False, sort_keys=True) if evidence else None,
                status,
            ),
        )
        return issue_id

    def clear_for_plan(self, plan_id: str) -> int:
        cursor = self.connection.execute(
            "DELETE FROM workflow_issue WHERE plan_id = ?",
            (plan_id,),
        )
        return cursor.rowcount

    def list(
        self,
        plan_id: str | None = None,
        task_id: str | None = None,
        severity: str | None = None,
        category: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if plan_id:
            conditions.append("plan_id = ?")
            params.append(plan_id)
        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if status:
            conditions.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM workflow_issue
            {where}
            ORDER BY
                CASE severity
                    WHEN 'error' THEN 1
                    WHEN 'warning' THEN 2
                    ELSE 3
                END,
                category,
                task_id,
                id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


class SourceDocumentRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def upsert(
        self,
        source_uri: str,
        source_type: str = "unknown",
        project_id: str | None = None,
        file_hash: str | None = None,
        title: str | None = None,
        parser_name: str | None = None,
        parser_version: str | None = None,
        metadata: dict[str, Any] | None = None,
        status: str = "active",
    ) -> str:
        document_id = new_id("src")
        self.connection.execute(
            """
            INSERT INTO source_document(
                id, project_id, source_uri, source_type, file_hash, title,
                parser_name, parser_version, metadata_json, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_uri) DO UPDATE SET
                project_id = excluded.project_id,
                source_type = excluded.source_type,
                file_hash = excluded.file_hash,
                title = excluded.title,
                parser_name = excluded.parser_name,
                parser_version = excluded.parser_version,
                metadata_json = excluded.metadata_json,
                status = excluded.status,
                updated_at = datetime('now')
            """,
            (
                document_id,
                project_id,
                source_uri,
                source_type,
                file_hash,
                title,
                parser_name,
                parser_version,
                json.dumps(metadata, ensure_ascii=False, sort_keys=True) if metadata else None,
                status,
            ),
        )
        row = self.connection.execute(
            "SELECT id FROM source_document WHERE source_uri = ?",
            (source_uri,),
        ).fetchone()
        return row["id"]

    def get(self, document_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM source_document WHERE id = ?",
            (document_id,),
        ).fetchone()
        return row_to_dict(row)

    def list(
        self,
        project_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"SELECT * FROM source_document {where} ORDER BY created_at, id",
            params,
        ).fetchall()
        return [dict(row) for row in rows]


class DrawingPageRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def upsert(
        self,
        source_document_id: str,
        drawing_id: str | None = None,
        page_no: int | None = None,
        layout_name: str | None = None,
        width: float | None = None,
        height: float | None = None,
        unit: str | None = None,
        scale: str | None = None,
        rotation: float = 0,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        existing = self.connection.execute(
            """
            SELECT id FROM drawing_page
            WHERE source_document_id = ?
              AND COALESCE(page_no, -1) = COALESCE(?, -1)
              AND COALESCE(layout_name, '') = COALESCE(?, '')
            """,
            (source_document_id, page_no, layout_name),
        ).fetchone()
        page_id = existing["id"] if existing else new_id("pg")
        if existing:
            self.connection.execute(
                """
                UPDATE drawing_page
                SET drawing_id = ?, width = ?, height = ?, unit = ?, scale = ?,
                    rotation = ?, metadata_json = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    drawing_id,
                    width,
                    height,
                    unit,
                    scale,
                    rotation,
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True) if metadata else None,
                    page_id,
                ),
            )
            return page_id
        self.connection.execute(
            """
            INSERT INTO drawing_page(
                id, source_document_id, drawing_id, page_no, layout_name,
                width, height, unit, scale, rotation, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page_id,
                source_document_id,
                drawing_id,
                page_no,
                layout_name,
                width,
                height,
                unit,
                scale,
                rotation,
                json.dumps(metadata, ensure_ascii=False, sort_keys=True) if metadata else None,
            ),
        )
        return page_id

    def get(self, page_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM drawing_page WHERE id = ?",
            (page_id,),
        ).fetchone()
        return row_to_dict(row)

    def list(self, source_document_id: str | None = None) -> list[dict[str, Any]]:
        if source_document_id:
            rows = self.connection.execute(
                """
                SELECT * FROM drawing_page
                WHERE source_document_id = ?
                ORDER BY page_no, layout_name, id
                """,
                (source_document_id,),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM drawing_page ORDER BY source_document_id, page_no, layout_name, id"
            ).fetchall()
        return [dict(row) for row in rows]


class DrawingPrimitiveRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def upsert(
        self,
        page_id: str,
        source_local_id: str,
        primitive_type: str = "unknown",
        geometry: dict[str, Any] | None = None,
        bbox: dict[str, Any] | None = None,
        text: str | None = None,
        style: dict[str, Any] | None = None,
        raw: dict[str, Any] | None = None,
        confidence: float = 1.0,
    ) -> str:
        primitive_id = new_id("prim")
        self.connection.execute(
            """
            INSERT INTO drawing_primitive(
                id, page_id, source_local_id, primitive_type, geometry_json,
                bbox_json, text, style_json, raw_json, confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(page_id, source_local_id) DO UPDATE SET
                primitive_type = excluded.primitive_type,
                geometry_json = excluded.geometry_json,
                bbox_json = excluded.bbox_json,
                text = excluded.text,
                style_json = excluded.style_json,
                raw_json = excluded.raw_json,
                confidence = excluded.confidence,
                updated_at = datetime('now')
            """,
            (
                primitive_id,
                page_id,
                source_local_id,
                primitive_type,
                _json_or_none(geometry),
                _json_or_none(bbox),
                text,
                _json_or_none(style),
                _json_or_none(raw),
                confidence,
            ),
        )
        row = self.connection.execute(
            "SELECT id FROM drawing_primitive WHERE page_id = ? AND source_local_id = ?",
            (page_id, source_local_id),
        ).fetchone()
        return row["id"]

    def list(self, page_id: str | None = None) -> list[dict[str, Any]]:
        if page_id:
            rows = self.connection.execute(
                "SELECT * FROM drawing_primitive WHERE page_id = ? ORDER BY source_local_id, id",
                (page_id,),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM drawing_primitive ORDER BY page_id, source_local_id, id"
            ).fetchall()
        return [dict(row) for row in rows]


class RecognitionCandidateRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def upsert(
        self,
        page_id: str,
        source_local_id: str,
        candidate_type: str = "unknown",
        class_code: str | None = None,
        label: str | None = None,
        confidence: float = 1.0,
        source: str = "import",
        model_name: str | None = None,
        model_version: str | None = None,
        geometry: dict[str, Any] | None = None,
        bbox: dict[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
        status: str = "pending",
    ) -> str:
        candidate_id = new_id("rcog")
        self.connection.execute(
            """
            INSERT INTO recognition_candidate(
                id, page_id, source_local_id, candidate_type, class_code,
                label, confidence, source, model_name, model_version,
                geometry_json, bbox_json, attributes_json, evidence_json, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(page_id, source_local_id) DO UPDATE SET
                candidate_type = excluded.candidate_type,
                class_code = excluded.class_code,
                label = excluded.label,
                confidence = excluded.confidence,
                source = excluded.source,
                model_name = excluded.model_name,
                model_version = excluded.model_version,
                geometry_json = excluded.geometry_json,
                bbox_json = excluded.bbox_json,
                attributes_json = excluded.attributes_json,
                evidence_json = excluded.evidence_json,
                status = excluded.status,
                updated_at = datetime('now')
            """,
            (
                candidate_id,
                page_id,
                source_local_id,
                candidate_type,
                class_code,
                label,
                confidence,
                source,
                model_name,
                model_version,
                _json_or_none(geometry),
                _json_or_none(bbox),
                _json_or_none(attributes),
                _json_or_none(evidence),
                status,
            ),
        )
        row = self.connection.execute(
            "SELECT id FROM recognition_candidate WHERE page_id = ? AND source_local_id = ?",
            (page_id, source_local_id),
        ).fetchone()
        return row["id"]

    def link_primitive(
        self,
        candidate_id: str,
        primitive_id: str,
        role: str = "context",
        weight: float = 1.0,
        evidence: dict[str, Any] | None = None,
    ) -> str:
        link_id = new_id("rcl")
        self.connection.execute(
            """
            INSERT INTO recognition_candidate_primitive(
                id, candidate_id, primitive_id, role, weight, evidence_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_id, primitive_id, role) DO UPDATE SET
                weight = excluded.weight,
                evidence_json = excluded.evidence_json
            """,
            (link_id, candidate_id, primitive_id, role, weight, _json_or_none(evidence)),
        )
        row = self.connection.execute(
            """
            SELECT id FROM recognition_candidate_primitive
            WHERE candidate_id = ? AND primitive_id = ? AND role = ?
            """,
            (candidate_id, primitive_id, role),
        ).fetchone()
        return row["id"]

    def update_status(self, candidate_id: str, status: str) -> None:
        self.connection.execute(
            "UPDATE recognition_candidate SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, candidate_id),
        )

    def list(
        self,
        page_id: str | None = None,
        class_code: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if page_id:
            conditions.append("page_id = ?")
            params.append(page_id)
        if class_code:
            conditions.append("class_code = ?")
            params.append(class_code)
        if status:
            conditions.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"SELECT * FROM recognition_candidate {where} ORDER BY page_id, source_local_id, id",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def linked_candidate_ids(self, hypothesis_id: str) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT candidate_id
            FROM hypothesis_candidate
            WHERE hypothesis_id = ?
            ORDER BY role, candidate_id
            """,
            (hypothesis_id,),
        ).fetchall()
        return [row["candidate_id"] for row in rows]


class ObjectHypothesisRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def upsert(
        self,
        page_id: str,
        source_document_id: str,
        class_code: str,
        source_local_id: str,
        subtype: str | None = None,
        confidence: float = 1.0,
        geometry: dict[str, Any] | None = None,
        bbox: dict[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
        status: str = "pending",
    ) -> str:
        hypothesis_id = new_id("hyp")
        self.connection.execute(
            """
            INSERT INTO object_hypothesis(
                id, page_id, source_document_id, class_code, subtype,
                source_local_id, confidence, geometry_json, bbox_json,
                attributes_json, evidence_json, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(page_id, source_local_id) DO UPDATE SET
                source_document_id = excluded.source_document_id,
                class_code = excluded.class_code,
                subtype = excluded.subtype,
                confidence = excluded.confidence,
                geometry_json = excluded.geometry_json,
                bbox_json = excluded.bbox_json,
                attributes_json = excluded.attributes_json,
                evidence_json = excluded.evidence_json,
                status = excluded.status,
                updated_at = datetime('now')
            """,
            (
                hypothesis_id,
                page_id,
                source_document_id,
                class_code,
                subtype,
                source_local_id,
                confidence,
                _json_or_none(geometry),
                _json_or_none(bbox),
                _json_or_none(attributes),
                _json_or_none(evidence),
                status,
            ),
        )
        row = self.connection.execute(
            "SELECT id FROM object_hypothesis WHERE page_id = ? AND source_local_id = ?",
            (page_id, source_local_id),
        ).fetchone()
        return row["id"]

    def link_candidate(
        self,
        hypothesis_id: str,
        candidate_id: str,
        role: str = "primary",
        weight: float = 1.0,
        evidence: dict[str, Any] | None = None,
    ) -> str:
        link_id = new_id("hcl")
        self.connection.execute(
            """
            INSERT INTO hypothesis_candidate(
                id, hypothesis_id, candidate_id, role, weight, evidence_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(hypothesis_id, candidate_id, role) DO UPDATE SET
                weight = excluded.weight,
                evidence_json = excluded.evidence_json
            """,
            (link_id, hypothesis_id, candidate_id, role, weight, _json_or_none(evidence)),
        )
        row = self.connection.execute(
            """
            SELECT id FROM hypothesis_candidate
            WHERE hypothesis_id = ? AND candidate_id = ? AND role = ?
            """,
            (hypothesis_id, candidate_id, role),
        ).fetchone()
        return row["id"]

    def get(self, hypothesis_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM object_hypothesis WHERE id = ?",
            (hypothesis_id,),
        ).fetchone()
        return row_to_dict(row)

    def update_status(self, hypothesis_id: str, status: str) -> None:
        self.connection.execute(
            "UPDATE object_hypothesis SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, hypothesis_id),
        )

    def list(
        self,
        page_id: str | None = None,
        class_code: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if page_id:
            conditions.append("page_id = ?")
            params.append(page_id)
        if class_code:
            conditions.append("class_code = ?")
            params.append(class_code)
        if status:
            conditions.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"SELECT * FROM object_hypothesis {where} ORDER BY page_id, source_local_id, id",
            params,
        ).fetchall()
        return [dict(row) for row in rows]


class HypothesisToObjectRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def create(
        self,
        hypothesis_id: str,
        object_id: str,
        accepted_by: str | None = None,
        acceptance_method: str = "manual",
        evidence: dict[str, Any] | None = None,
    ) -> str:
        mapping_id = new_id("hobj")
        self.connection.execute(
            """
            INSERT INTO hypothesis_to_object(
                id, hypothesis_id, object_id, accepted_by, acceptance_method, evidence_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(hypothesis_id) DO UPDATE SET
                object_id = excluded.object_id,
                accepted_by = excluded.accepted_by,
                acceptance_method = excluded.acceptance_method,
                evidence_json = excluded.evidence_json
            """,
            (
                mapping_id,
                hypothesis_id,
                object_id,
                accepted_by,
                acceptance_method,
                _json_or_none(evidence),
            ),
        )
        row = self.connection.execute(
            "SELECT id FROM hypothesis_to_object WHERE hypothesis_id = ?",
            (hypothesis_id,),
        ).fetchone()
        return row["id"]

    def find_by_hypothesis(self, hypothesis_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM hypothesis_to_object WHERE hypothesis_id = ?",
            (hypothesis_id,),
        ).fetchone()
        return row_to_dict(row)

    def list(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM hypothesis_to_object ORDER BY created_at, id"
        ).fetchall()
        return [dict(row) for row in rows]


class RuleTemplateRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def create(self, rule: RuleTemplateInput) -> str:
        rule_id = new_id("rule")
        self.connection.execute(
            """
            INSERT INTO rule_template(
                id, name, version, rule_kind, source_class, target_class,
                relation_type, max_distance, expression, min_confidence,
                enabled, priority, config_json, valid_from, valid_to
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rule_id,
                rule.name,
                rule.version,
                rule.rule_kind,
                rule.source_class,
                rule.target_class,
                rule.relation_type,
                rule.max_distance,
                rule.expression,
                rule.min_confidence,
                1 if rule.enabled else 0,
                rule.priority,
                json.dumps(rule.config, ensure_ascii=False) if rule.config else None,
                rule.valid_from,
                rule.valid_to,
            ),
        )
        return rule_id

    def enabled(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM rule_template WHERE enabled = 1 ORDER BY priority, created_at"
        ).fetchall()
        return [dict(row) for row in rows]


class ManualCorrectionRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def correct_relation(
        self,
        source_id: str,
        old_target_id: str | None,
        new_target_id: str,
        relation_type: str,
        original_relation_id: str | None = None,
        reason: str | None = None,
        operator: str | None = None,
    ) -> str:
        correction_id = new_id("mrel")
        self.connection.execute(
            """
            INSERT INTO manual_relation(
                id, original_relation_id, source_id, old_target_id,
                new_target_id, relation_type, reason, operator
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                correction_id,
                original_relation_id,
                source_id,
                old_target_id,
                new_target_id,
                relation_type,
                reason,
                operator,
            ),
        )
        if original_relation_id:
            self.connection.execute(
                "UPDATE relation SET status = 'overridden', updated_at = datetime('now') WHERE id = ?",
                (original_relation_id,),
            )
        RelationRepository(self.connection).upsert(
            source_id=source_id,
            target_id=new_target_id,
            relation_type=relation_type,
            confidence=1.0,
            source="manual",
            evidence={"manual_correction_id": correction_id, "reason": reason},
        )
        CorrectionLogRepository(self.connection).add(
            entity_type="relation",
            entity_id=original_relation_id or correction_id,
            field_name=relation_type,
            old_value=old_target_id,
            new_value=new_target_id,
            operator=operator,
            reason=reason,
        )
        return correction_id


class CorrectionLogRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def add(
        self,
        entity_type: str,
        entity_id: str,
        field_name: str,
        old_value: Any,
        new_value: Any,
        operator: str | None = None,
        reason: str | None = None,
    ) -> str:
        correction_id = new_id("cor")
        self.connection.execute(
            """
            INSERT INTO correction_log(
                id, entity_type, entity_id, field_name, old_value, new_value, operator, reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                correction_id,
                entity_type,
                entity_id,
                field_name,
                json.dumps(old_value, ensure_ascii=False) if isinstance(old_value, (dict, list)) else old_value,
                json.dumps(new_value, ensure_ascii=False) if isinstance(new_value, (dict, list)) else new_value,
                operator,
                reason,
            ),
        )
        return correction_id

    def list(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)
        if entity_id:
            conditions.append("entity_id = ?")
            params.append(entity_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM correction_log
            {where}
            ORDER BY created_at, id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def seed_rules(connection: sqlite3.Connection, rules: Iterable[RuleTemplateInput]) -> None:
    repository = RuleTemplateRepository(connection)
    for rule in rules:
        existing = connection.execute(
            "SELECT id FROM rule_template WHERE name = ?",
            (rule.name,),
        ).fetchone()
        if existing:
            continue
        repository.create(rule)
