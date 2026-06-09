from __future__ import annotations

import math
import sqlite3


class SpatialIndex:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def nearest(
        self,
        object_id: str,
        target_class: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        source = self.connection.execute(
            "SELECT center_x, center_y FROM geometry WHERE object_id = ?",
            (object_id,),
        ).fetchone()
        if not source or source["center_x"] is None or source["center_y"] is None:
            return []

        params: list[object] = [object_id]
        class_filter = ""
        if target_class:
            class_filter = "AND o.class = ?"
            params.append(target_class)

        rows = self.connection.execute(
            f"""
            SELECT o.id, o.class, o.subtype, o.confidence, g.center_x, g.center_y
            FROM geometry g
            JOIN cad_object o ON o.id = g.object_id
            WHERE g.object_id <> ?
              AND g.center_x IS NOT NULL
              AND g.center_y IS NOT NULL
              {class_filter}
            """,
            params,
        ).fetchall()

        candidates = []
        for row in rows:
            distance = math.dist(
                (float(source["center_x"]), float(source["center_y"])),
                (float(row["center_x"]), float(row["center_y"])),
            )
            item = dict(row)
            item["distance"] = distance
            candidates.append(item)
        return sorted(candidates, key=lambda item: item["distance"])[:limit]

    def contains_point(self, x: float, y: float, class_name: str | None = None) -> list[dict]:
        params: list[object] = [x, x, y, y]
        class_filter = ""
        if class_name:
            class_filter = "AND o.class = ?"
            params.append(class_name)
        rows = self.connection.execute(
            f"""
            SELECT o.*, r.min_x, r.max_x, r.min_y, r.max_y
            FROM geometry_rtree r
            JOIN geometry_rtree_map m ON m.rowid = r.rowid
            JOIN cad_object o ON o.id = m.object_id
            WHERE r.min_x <= ?
              AND r.max_x >= ?
              AND r.min_y <= ?
              AND r.max_y >= ?
              {class_filter}
            ORDER BY o.class, o.id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def overlap(
        self,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
        class_name: str | None = None,
    ) -> list[dict]:
        params: list[object] = [max_x, min_x, max_y, min_y]
        class_filter = ""
        if class_name:
            class_filter = "AND o.class = ?"
            params.append(class_name)
        rows = self.connection.execute(
            f"""
            SELECT o.*, r.min_x, r.max_x, r.min_y, r.max_y
            FROM geometry_rtree r
            JOIN geometry_rtree_map m ON m.rowid = r.rowid
            JOIN cad_object o ON o.id = m.object_id
            WHERE r.min_x <= ?
              AND r.max_x >= ?
              AND r.min_y <= ?
              AND r.max_y >= ?
              {class_filter}
            ORDER BY o.class, o.id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
