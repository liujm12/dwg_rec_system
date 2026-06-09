from __future__ import annotations

import sqlite3

from ..repositories import RelationCandidateRepository, RelationRepository, RuleTemplateRepository
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
                evidence = {
                    "rule": rule["name"],
                    "rule_version": rule["version"],
                    "distance": candidate["distance"],
                    "source_class": rule["source_class"],
                    "target_class": rule["target_class"],
                }
                candidate_id = self.candidates.upsert(
                    source_id=source["id"],
                    target_id=candidate["id"],
                    relation_type=rule["relation_type"],
                    confidence=confidence,
                    source="rule",
                    rule_id=rule["id"],
                    evidence=evidence,
                )
                relation_id = self.candidates.accept(candidate_id)
                inferred.append(
                    {
                        "id": relation_id,
                        "candidate_id": candidate_id,
                        "source_id": source["id"],
                        "target_id": candidate["id"],
                        "relation_type": rule["relation_type"],
                        "confidence": confidence,
                    }
                )
        return inferred

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
