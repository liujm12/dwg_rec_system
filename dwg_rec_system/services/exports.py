from __future__ import annotations

import csv
import sqlite3
from pathlib import Path


class CsvExporter:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def export_objects(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        rows = self.connection.execute(
            """
            SELECT
                o.id,
                o.class,
                o.subtype,
                o.source_file,
                o.handle,
                o.confidence,
                o.status,
                o.parser_name,
                o.parser_version,
                o.recognition_model,
                o.recognition_version,
                g.center_x,
                g.center_y,
                g.width,
                g.height,
                g.rotation,
                m.layer,
                m.block_name
            FROM cad_object o
            LEFT JOIN geometry g ON g.object_id = o.id
            LEFT JOIN cad_meta m ON m.object_id = o.id
            ORDER BY o.class, o.id
            """
        ).fetchall()
        fields = rows[0].keys() if rows else [
            "id",
            "class",
            "subtype",
            "source_file",
            "handle",
            "confidence",
            "status",
            "parser_name",
            "parser_version",
            "recognition_model",
            "recognition_version",
            "center_x",
            "center_y",
            "width",
            "height",
            "rotation",
            "layer",
            "block_name",
        ]
        with output.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(dict(row) for row in rows)
        return output

    def export_quantities(
        self,
        path: str | Path,
        project_id: str | None = None,
        drawing_id: str | None = None,
        class_code: str | None = None,
        status: str | None = None,
    ) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)

        conditions: list[str] = []
        params: list[str] = []
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
            SELECT
                id,
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
                status,
                confidence,
                source
            FROM quantity_item
            {where}
            ORDER BY class_code, group_key, source_object_id, id
            """,
            params,
        ).fetchall()
        fields = [
            "id",
            "project_id",
            "drawing_id",
            "source_object_id",
            "class_code",
            "discipline",
            "item_name",
            "spec",
            "unit",
            "quantity",
            "quantity_method",
            "group_key",
            "location",
            "system_code",
            "status",
            "confidence",
            "source",
        ]
        with output.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(dict(row) for row in rows)
        return output
