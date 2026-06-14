from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import RuleTemplateInput
from ..repositories import RuleTemplateRepository


class RuleTemplateSeeder:
    """Seed rule_template rows from a JSON rule package."""

    def __init__(self, connection):
        self.connection = connection
        self.rules = RuleTemplateRepository(connection)

    def seed_file(self, path: str | Path) -> dict[str, Any]:
        raw = Path(path).read_text(encoding="utf-8")
        payload = json.loads(raw)
        return self.seed_data(payload)

    def seed_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "rules" not in payload:
            raise ValueError("missing 'rules' in rule payload")
        if not isinstance(payload["rules"], list):
            raise ValueError("'rules' must be a list")

        created = 0
        skipped = 0
        errors: list[dict[str, Any]] = []

        for idx, raw_rule in enumerate(payload["rules"]):
            try:
                rule = self._build_rule(raw_rule)
                existing = self.connection.execute(
                    "SELECT id FROM rule_template WHERE name = ?",
                    (rule.name,),
                ).fetchone()
                if existing:
                    skipped += 1
                    continue
                self.rules.create(rule)
                created += 1
            except Exception as exc:
                errors.append(
                    {
                        "index": idx,
                        "name": raw_rule.get("name") if isinstance(raw_rule, dict) else None,
                        "error": str(exc),
                    }
                )

        return {
            "total": len(payload["rules"]),
            "created": created,
            "skipped": skipped,
            "errors": errors,
        }

    @staticmethod
    def _build_rule(raw: dict[str, Any]) -> RuleTemplateInput:
        if not isinstance(raw, dict):
            raise ValueError("rule entry must be an object")
        for field in ("name", "source_class", "target_class", "relation_type"):
            if not raw.get(field):
                raise ValueError(f"missing '{field}'")

        return RuleTemplateInput(
            name=raw["name"],
            source_class=raw["source_class"],
            target_class=raw["target_class"],
            relation_type=raw["relation_type"],
            version=str(raw.get("version", "1")),
            rule_kind=raw.get("rule_kind", "spatial"),
            max_distance=_float_or_none(raw.get("max_distance")),
            expression=raw.get("expression"),
            min_confidence=float(raw.get("min_confidence", 0.5)),
            priority=int(raw.get("priority", 100)),
            enabled=bool(raw.get("enabled", True)),
            config=raw.get("config"),
            valid_from=raw.get("valid_from"),
            valid_to=raw.get("valid_to"),
        )


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
