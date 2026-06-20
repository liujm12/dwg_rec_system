from __future__ import annotations

import csv
import json
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

    def export_quality_findings(
        self,
        path: str | Path,
        findings: list[dict],
    ) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "finding_id",
            "severity",
            "category",
            "code",
            "message",
            "project_id",
            "drawing_id",
            "object_id",
            "quantity_item_id",
            "class_code",
            "discipline",
            "profile_group",
            "field_name",
            "expected",
            "actual",
            "source",
            "evidence",
            "status",
        ]
        with output.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(_serialize_finding(item, fields) for item in findings)
        return output

    def export_budget(
        self,
        path: str | Path,
        project_id: str | None = None,
        drawing_id: str | None = None,
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
                status,
                confidence
            FROM budget_item
            {where}
            ORDER BY class_code, status, item_name, id
            """,
            params,
        ).fetchall()
        fields = [
            "id",
            "project_id",
            "drawing_id",
            "quantity_item_id",
            "cost_item_id",
            "class_code",
            "discipline",
            "item_name",
            "spec",
            "unit",
            "quantity",
            "unit_price_material",
            "unit_price_labor",
            "unit_price_machine",
            "material_cost",
            "labor_cost",
            "machine_cost",
            "total_cost",
            "pricing_source",
            "status",
            "confidence",
        ]
        with output.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(dict(row) for row in rows)
        return output

    def export_install_tasks(
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
                object_id,
                class_code,
                discipline,
                task_name,
                work_package,
                location,
                system_code,
                priority,
                status,
                confidence
            FROM install_task
            {where}
            ORDER BY work_package, class_code, task_name, id
            """,
            params,
        ).fetchall()
        fields = [
            "id",
            "project_id",
            "drawing_id",
            "object_id",
            "class_code",
            "discipline",
            "task_name",
            "work_package",
            "location",
            "system_code",
            "priority",
            "status",
            "confidence",
        ]
        with output.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(dict(row) for row in rows)
        return output


def _serialize_finding(finding: dict, fields: list[str]) -> dict:
    row = {field: finding.get(field) for field in fields}
    for key, value in row.items():
        if isinstance(value, (dict, list)):
            row[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return row
