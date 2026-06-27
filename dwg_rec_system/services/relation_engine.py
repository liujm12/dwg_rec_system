from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..repositories import RelationCandidateRepository, RelationRepository, RuleTemplateRepository
from ..spatial import bbox_center_distance, containment_ratio, normalize_bbox, overlap_ratios
from .spatial_index import SpatialIndex


class RelationEngine:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.rules = RuleTemplateRepository(connection)
        self.candidates = RelationCandidateRepository(connection)
        self.relations = RelationRepository(connection)
        self.spatial = SpatialIndex(connection)

    def infer(self) -> list[dict]:
        inferred: list[dict] = []
        for rule in self.rules.enabled():
            config = self._config(rule)
            strategy = config.get("strategy") or rule["rule_kind"] or "nearest"
            if strategy in {"spatial", "nearest"}:
                inferred.extend(self._infer_nearest(rule, config))
            elif strategy in {"bbox_containment", "containment"}:
                inferred.extend(self._infer_containment(rule, config))
            elif strategy in {"bbox_overlap", "overlap"}:
                inferred.extend(self._infer_overlap(rule, config))
            elif strategy in {"text_label_binding", "labels"}:
                inferred.extend(self._infer_labels(rule, config))
        return inferred

    def _infer_nearest(self, rule: dict[str, Any], config: dict[str, Any]) -> list[dict]:
        inferred: list[dict] = []
        source_objects = self.connection.execute(
            "SELECT id, confidence FROM cad_object WHERE class = ? AND status <> 'rejected'",
            (rule["source_class"],),
        ).fetchall()
        for source in source_objects:
            candidates = self.spatial.nearest(
                object_id=source["id"],
                target_class=rule["target_class"],
                limit=1,
            )
            if not candidates:
                continue
            candidate = candidates[0]
            max_distance = rule["max_distance"]
            if max_distance is not None and candidate["distance"] > max_distance:
                continue
            confidence = self._confidence(
                source_confidence=float(source["confidence"]),
                target_confidence=float(candidate["confidence"]),
                distance=float(candidate["distance"]),
                max_distance=max_distance,
            )
            if confidence < float(rule["min_confidence"]):
                continue
            evidence = self._base_evidence(rule, "nearest")
            evidence.update({"distance": candidate["distance"]})
            inferred.append(
                self._write_candidate(
                    rule=rule,
                    source_id=source["id"],
                    target_id=candidate["id"],
                    confidence=confidence,
                    evidence=evidence,
                    auto_accept=bool(config.get("auto_accept", True)),
                )
            )
        return inferred

    def _infer_containment(self, rule: dict[str, Any], config: dict[str, Any]) -> list[dict]:
        threshold = float(config.get("threshold", config.get("containment_threshold", 0.9)))
        results: list[dict] = []
        for source in self._objects(rule["source_class"]):
            for target in self._objects(rule["target_class"]):
                if source["id"] == target["id"]:
                    continue
                if rule["relation_type"] == "located_in":
                    container = target
                    contained = source
                else:
                    container = source
                    contained = target
                ratio = containment_ratio(container["bbox"], contained["bbox"])
                if ratio < threshold:
                    continue
                confidence = self._bounded_confidence(source, target, 0.7 + 0.25 * ratio)
                if confidence < float(rule["min_confidence"]):
                    continue
                evidence = self._base_evidence(rule, "bbox_containment")
                evidence.update(
                    {
                        "container_bbox": container["bbox"],
                        "contained_bbox": contained["bbox"],
                        "containment_ratio": ratio,
                        "threshold": threshold,
                    }
                )
                results.append(
                    self._write_candidate(
                        rule=rule,
                        source_id=source["id"],
                        target_id=target["id"],
                        confidence=confidence,
                        evidence=evidence,
                        auto_accept=bool(config.get("auto_accept", False)),
                    )
                )
        return results

    def _infer_overlap(self, rule: dict[str, Any], config: dict[str, Any]) -> list[dict]:
        threshold = float(config.get("threshold", config.get("overlap_threshold", 0.5)))
        results: list[dict] = []
        for source in self._objects(rule["source_class"]):
            for target in self._objects(rule["target_class"]):
                if source["id"] == target["id"]:
                    continue
                ratios = overlap_ratios(source["bbox"], target["bbox"])
                score = min(ratios["source_overlap_ratio"], ratios["target_overlap_ratio"])
                if score < threshold:
                    continue
                confidence = self._bounded_confidence(source, target, 0.55 + 0.3 * score)
                if confidence < float(rule["min_confidence"]):
                    continue
                evidence = self._base_evidence(rule, "bbox_overlap")
                evidence.update(
                    {
                        "source_bbox": source["bbox"],
                        "target_bbox": target["bbox"],
                        "threshold": threshold,
                        **ratios,
                    }
                )
                results.append(
                    self._write_candidate(
                        rule=rule,
                        source_id=source["id"],
                        target_id=target["id"],
                        confidence=confidence,
                        evidence=evidence,
                        auto_accept=bool(config.get("auto_accept", False)),
                    )
                )
        return results

    def _infer_labels(self, rule: dict[str, Any], config: dict[str, Any]) -> list[dict]:
        max_distance = float(config.get("max_distance", rule["max_distance"] or 50.0))
        results: list[dict] = []
        targets = self._objects(rule["target_class"])
        for label in self._objects(rule["source_class"], include_attributes=True):
            label_text = self._label_text(label)
            if not label_text:
                continue
            nearest: tuple[dict[str, Any], float] | None = None
            for target in targets:
                if label["id"] == target["id"]:
                    continue
                distance = bbox_center_distance(label["bbox"], target["bbox"])
                if distance is None or distance > max_distance:
                    continue
                if nearest is None or distance < nearest[1]:
                    nearest = (target, distance)
            if not nearest:
                continue
            target, distance = nearest
            distance_score = 1.0 - distance / max_distance if max_distance > 0 else 1.0
            confidence = self._bounded_confidence(label, target, 0.65 + 0.25 * distance_score)
            if confidence < float(rule["min_confidence"]):
                continue
            evidence = self._base_evidence(rule, "text_label_binding")
            evidence.update(
                {
                    "label_text": label_text,
                    "distance": distance,
                    "max_distance": max_distance,
                    "text_bbox": label["bbox"],
                    "target_bbox": target["bbox"],
                }
            )
            results.append(
                self._write_candidate(
                    rule=rule,
                    source_id=label["id"],
                    target_id=target["id"],
                    confidence=confidence,
                    evidence=evidence,
                    auto_accept=bool(config.get("auto_accept", False)),
                )
            )
        return results

    def _objects(self, class_name: str, include_attributes: bool = False) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT
                o.id, o.class, o.subtype, o.confidence,
                g.min_x, g.min_y, g.max_x, g.max_y
            FROM cad_object o
            JOIN geometry g ON g.object_id = o.id
            WHERE o.class = ?
              AND o.status <> 'rejected'
            ORDER BY o.id
            """,
            (class_name,),
        ).fetchall()
        objects = []
        for row in rows:
            item = dict(row)
            bbox = normalize_bbox(item)
            if not bbox:
                continue
            item["bbox"] = bbox
            if include_attributes:
                item["attributes"] = self._attributes(item["id"])
            objects.append(item)
        return objects

    def _attributes(self, object_id: str) -> dict[str, str | None]:
        rows = self.connection.execute(
            "SELECT key, value FROM attribute WHERE object_id = ?",
            (object_id,),
        ).fetchall()
        return {row["key"]: row["value"] for row in rows}

    def _label_text(self, label: dict[str, Any]) -> str | None:
        attributes = label.get("attributes") or {}
        for key in ("text", "label", "tag", "name"):
            value = attributes.get(key)
            if value:
                return str(value)
        return None

    def _write_candidate(
        self,
        rule: dict[str, Any],
        source_id: str,
        target_id: str,
        confidence: float,
        evidence: dict[str, Any],
        auto_accept: bool,
    ) -> dict:
        candidate_id = self.candidates.upsert(
            source_id=source_id,
            target_id=target_id,
            relation_type=rule["relation_type"],
            confidence=confidence,
            source="rule",
            rule_id=rule["id"],
            evidence=evidence,
        )
        relation_id = self.candidates.accept(candidate_id) if auto_accept else None
        return {
            "id": relation_id,
            "candidate_id": candidate_id,
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": rule["relation_type"],
            "confidence": confidence,
            "status": "accepted" if auto_accept else "pending",
            "strategy": evidence["strategy"],
        }

    @staticmethod
    def _config(rule: dict[str, Any]) -> dict[str, Any]:
        if not rule.get("config_json"):
            return {}
        return json.loads(rule["config_json"])

    @staticmethod
    def _base_evidence(rule: dict[str, Any], strategy: str) -> dict[str, Any]:
        return {
            "rule": rule["name"],
            "rule_version": rule["version"],
            "strategy": strategy,
            "source_class": rule["source_class"],
            "target_class": rule["target_class"],
            "relation_type": rule["relation_type"],
        }

    @staticmethod
    def _bounded_confidence(source: dict[str, Any], target: dict[str, Any], strategy_score: float) -> float:
        return round(
            max(0.0, min(1.0, float(source["confidence"]) * float(target["confidence"]) * strategy_score)),
            4,
        )

    @staticmethod
    def _confidence(
        source_confidence: float,
        target_confidence: float,
        distance: float,
        max_distance: float | None,
    ) -> float:
        if max_distance is None or max_distance <= 0:
            distance_score = 1.0
        else:
            distance_score = max(0.0, 1.0 - distance / max_distance)
        return round(source_confidence * target_confidence * (0.5 + 0.5 * distance_score), 4)
