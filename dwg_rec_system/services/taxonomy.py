from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..repositories import ObjectClassRepository


class TaxonomySeeder:
    """Seed object_class table from the taxonomy JSON file.

    Idempotent: repeated runs will not duplicate existing classes.
    """

    def __init__(self, connection):
        self.connection = connection
        self.classes = ObjectClassRepository(connection)

    def seed_file(self, path: str | Path | None = None) -> dict[str, Any]:
        if path is None:
            path = (
                Path(__file__).resolve().parent.parent
                / "taxonomy"
                / "cleanroom_cad_taxonomy.json"
            )

        raw = Path(path).read_text(encoding="utf-8")
        taxonomy = json.loads(raw)
        return self.seed_data(taxonomy)

    def seed_data(self, taxonomy: dict[str, Any]) -> dict[str, Any]:
        entries = taxonomy.get("object_classes", [])
        created = 0
        skipped = 0
        errors: list[dict[str, Any]] = []

        for idx, entry in enumerate(entries):
            try:
                code = entry.get("code")
                if not code:
                    errors.append({"index": idx, "error": "missing 'code'"})
                    continue

                name_cn = entry.get("name_cn", code)
                discipline = entry.get("discipline")
                parent_code = entry.get("parent_code")

                # Build a rich description from aliases, attributes, and relations
                description = self._build_description(entry)

                # Check if already exists (idempotent)
                existing = self.connection.execute(
                    "SELECT id FROM object_class WHERE code = ?",
                    (code,),
                ).fetchone()

                if existing:
                    # Update existing record with latest data
                    self.connection.execute(
                        """
                        UPDATE object_class
                        SET name = ?, parent_code = ?, discipline = ?, description = ?,
                            updated_at = datetime('now')
                        WHERE code = ?
                        """,
                        (name_cn, parent_code, discipline, description, code),
                    )
                    skipped += 1
                else:
                    self.classes.get_or_create(
                        code=code,
                        name=name_cn,
                        parent_code=parent_code,
                        discipline=discipline,
                        description=description,
                    )
                    created += 1

            except Exception as exc:
                errors.append(
                    {"index": idx, "code": entry.get("code"), "error": str(exc)}
                )

        return {
            "total": len(entries),
            "created": created,
            "skipped": skipped,
            "errors": errors,
        }

    @staticmethod
    def _build_description(entry: dict[str, Any]) -> str:
        parts: list[str] = []

        aliases = entry.get("aliases", [])
        if aliases:
            parts.append("别名: " + ", ".join(aliases))

        attrs = entry.get("attributes", [])
        if attrs:
            parts.append("属性: " + ", ".join(attrs))

        relations = entry.get("relations", [])
        if relations:
            parts.append("关系: " + ", ".join(relations))

        return "; ".join(parts) if parts else entry.get("name_cn", entry.get("code", ""))
