from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..repositories import ObjectClassRepository


class TaxonomySeeder:
    """Seed object_class table from taxonomy JSON.

    Idempotent: repeated runs update existing classes and do not duplicate rows.
    Rich taxonomy profile fields are summarized into object_class.description
    until the project promotes stable profile fields into dedicated tables.
    """

    def __init__(self, connection):
        self.connection = connection
        self.classes = ObjectClassRepository(connection)

    def seed_file(self, path: str | Path | None = None) -> dict[str, Any]:
        if path is None:
            path = (
                Path(__file__).resolve().parent.parent
                / "taxonomy"
                / "cad_object_taxonomy.json"
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
                description = self._build_description(entry)

                existing = self.connection.execute(
                    "SELECT id FROM object_class WHERE code = ?",
                    (code,),
                ).fetchone()

                if existing:
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
            parts.append("aliases: " + ", ".join(aliases))

        attrs = entry.get("expected_attributes") or entry.get("attributes", [])
        if attrs:
            parts.append("attributes: " + ", ".join(attrs))

        relations = entry.get("relations", [])
        if relations:
            parts.append("relations: " + ", ".join(relations))

        budget = entry.get("budget")
        if isinstance(budget, dict):
            budget_bits = []
            if budget.get("unit"):
                budget_bits.append(f"unit={budget['unit']}")
            if budget.get("quantity_method"):
                budget_bits.append(f"method={budget['quantity_method']}")
            if budget.get("group_by"):
                budget_bits.append("group_by=" + ",".join(budget["group_by"]))
            if budget_bits:
                parts.append("budget: " + "; ".join(budget_bits))

        installation = entry.get("installation")
        if isinstance(installation, dict):
            install_bits = []
            if installation.get("work_package"):
                install_bits.append(f"work_package={installation['work_package']}")
            if installation.get("default_steps"):
                install_bits.append("steps=" + ",".join(installation["default_steps"]))
            if installation.get("required_predecessors"):
                install_bits.append(
                    "predecessors=" + ",".join(installation["required_predecessors"])
                )
            if install_bits:
                parts.append("installation: " + "; ".join(install_bits))

        return "; ".join(parts) if parts else entry.get("name_cn", entry.get("code", ""))
