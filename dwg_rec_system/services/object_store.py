from __future__ import annotations

import sqlite3

from ..models import ObjectInput
from ..repositories import (
    AttributeRepository,
    CadMetaRepository,
    GeometryRepository,
    ObjectRepository,
)


class ObjectStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.objects = ObjectRepository(connection)
        self.geometry = GeometryRepository(connection)
        self.cad_meta = CadMetaRepository(connection)
        self.attributes = AttributeRepository(connection)

    def create_object(self, data: ObjectInput) -> str:
        object_id = self.objects.find_by_source_handle(data.source_file, data.handle)
        if object_id:
            self.connection.execute(
                """
                UPDATE cad_object
                SET drawing_id = ?,
                    import_job_id = ?,
                    class_id = ?,
                    class = ?,
                    subtype = ?,
                    confidence = ?,
                    status = ?,
                    parser_name = ?,
                    parser_version = ?,
                    recognition_model = ?,
                    recognition_version = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    data.drawing_id,
                    data.import_job_id,
                    data.class_id,
                    data.class_name,
                    data.subtype,
                    data.confidence,
                    data.status,
                    data.parser_name,
                    data.parser_version,
                    data.recognition_model,
                    data.recognition_version,
                    object_id,
                ),
            )
        else:
            object_id = self.objects.create(
                class_name=data.class_name,
                subtype=data.subtype,
                source_file=data.source_file,
                handle=data.handle,
                drawing_id=data.drawing_id,
                import_job_id=data.import_job_id,
                class_id=data.class_id,
                confidence=data.confidence,
                status=data.status,
                parser_name=data.parser_name,
                parser_version=data.parser_version,
                recognition_model=data.recognition_model,
                recognition_version=data.recognition_version,
            )
        if data.geometry:
            self.geometry.upsert(object_id, data.geometry)
        if data.cad_meta:
            self.cad_meta.upsert(object_id, data.cad_meta)
        if data.attributes:
            self.attributes.bulk_set(object_id, data.attributes)
        return object_id

    def get_object_detail(self, object_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT
                o.*,
                g.center_x,
                g.center_y,
                g.width,
                g.height,
                g.rotation,
                g.min_x,
                g.min_y,
                g.max_x,
                g.max_y,
                m.layer,
                m.block_name,
                m.color,
                m.linetype,
                m.owner_block
            FROM cad_object o
            LEFT JOIN geometry g ON g.object_id = o.id
            LEFT JOIN cad_meta m ON m.object_id = o.id
            WHERE o.id = ?
            """,
            (object_id,),
        ).fetchone()
        if not row:
            return None
        attributes = self.connection.execute(
            "SELECT key, value, value_type, confidence, source FROM attribute WHERE object_id = ? ORDER BY key",
            (object_id,),
        ).fetchall()
        result = dict(row)
        result["attributes"] = [dict(item) for item in attributes]
        return result

    def list_objects(self, class_name: str | None = None) -> list[dict]:
        return self.objects.list(class_name)
