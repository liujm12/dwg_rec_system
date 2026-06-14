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
