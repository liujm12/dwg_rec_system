from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..models import GeometryInput
from ..repositories import (
    AttributeRepository,
    CorrectionLogRepository,
    GeometryRepository,
    ObjectClassRepository,
    ObjectHypothesisRepository,
    RelationCandidateRepository,
)
from ..spatial import bbox_iou, normalize_bbox
from .recognition import HypothesisAcceptanceService


class ReviewService:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.corrections = CorrectionLogRepository(connection)

    def review_relation_candidate(
        self,
        candidate_id: str,
        action: str,
        operator: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        candidates = RelationCandidateRepository(self.connection)
        before = candidates.get(candidate_id)
        if not before:
            raise ValueError(f"relation candidate not found: {candidate_id}")
        if action == "accept":
            relation_id = candidates.accept(candidate_id)
            new_status = "accepted"
        elif action == "reject":
            candidates.reject(candidate_id)
            relation_id = None
            new_status = "rejected"
        else:
            raise ValueError(f"unsupported relation candidate review action: {action}")
        self.corrections.add(
            entity_type="relation_candidate",
            entity_id=candidate_id,
            field_name="status",
            old_value=before["status"],
            new_value=new_status,
            operator=operator,
            reason=reason,
        )
        return {
            "candidate_id": candidate_id,
            "action": action,
            "old_status": before["status"],
            "new_status": new_status,
            "relation_id": relation_id,
        }

    def review_object_hypothesis(
        self,
        hypothesis_id: str,
        action: str,
        operator: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        hypotheses = ObjectHypothesisRepository(self.connection)
        before = hypotheses.get(hypothesis_id)
        if not before:
            raise ValueError(f"object hypothesis not found: {hypothesis_id}")
        if action == "accept":
            result = HypothesisAcceptanceService(self.connection).accept(
                hypothesis_id=hypothesis_id,
                accepted_by=operator,
                acceptance_method="manual",
            )
            new_status = "accepted"
        elif action == "reject":
            hypotheses.update_status(hypothesis_id, "rejected")
            result = {"hypothesis_id": hypothesis_id, "object_id": None}
            new_status = "rejected"
        else:
            raise ValueError(f"unsupported object hypothesis review action: {action}")
        self.corrections.add(
            entity_type="object_hypothesis",
            entity_id=hypothesis_id,
            field_name="status",
            old_value=before["status"],
            new_value=new_status,
            operator=operator,
            reason=reason,
        )
        return {
            **result,
            "action": action,
            "old_status": before["status"],
            "new_status": new_status,
        }


class ObjectCorrectionService:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.corrections = CorrectionLogRepository(connection)

    def correct_class(
        self,
        object_id: str,
        class_code: str,
        operator: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        obj = self._object(object_id)
        class_row = ObjectClassRepository(self.connection).find_by_code(class_code)
        self.connection.execute(
            """
            UPDATE cad_object
            SET class = ?, class_id = ?, status = 'corrected', updated_at = datetime('now')
            WHERE id = ?
            """,
            (class_code, class_row["id"] if class_row else None, object_id),
        )
        self.corrections.add(
            entity_type="object",
            entity_id=object_id,
            field_name="class",
            old_value=obj["class"],
            new_value=class_code,
            operator=operator,
            reason=reason,
        )
        return {"object_id": object_id, "field": "class", "old_value": obj["class"], "new_value": class_code}

    def set_attribute(
        self,
        object_id: str,
        key: str,
        value: str | None,
        namespace: str = "default",
        operator: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        self._object(object_id)
        old_row = self.connection.execute(
            """
            SELECT value
            FROM attribute
            WHERE object_id = ? AND namespace = ? AND key = ?
            """,
            (object_id, namespace, key),
        ).fetchone()
        AttributeRepository(self.connection).set(
            object_id=object_id,
            key=key,
            value=value,
            namespace=namespace,
            source="manual",
            confidence=1.0,
        )
        self.connection.execute(
            "UPDATE cad_object SET status = 'corrected', updated_at = datetime('now') WHERE id = ?",
            (object_id,),
        )
        old_value = old_row["value"] if old_row else None
        self.corrections.add(
            entity_type="attribute",
            entity_id=object_id,
            field_name=f"{namespace}.{key}",
            old_value=old_value,
            new_value=value,
            operator=operator,
            reason=reason,
        )
        return {"object_id": object_id, "field": f"{namespace}.{key}", "old_value": old_value, "new_value": value}

    def correct_bbox(
        self,
        object_id: str,
        bbox: dict[str, Any],
        operator: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        self._object(object_id)
        normalized = normalize_bbox(bbox)
        if not normalized:
            raise ValueError("invalid bbox")
        old_row = self.connection.execute(
            "SELECT min_x, min_y, max_x, max_y FROM geometry WHERE object_id = ?",
            (object_id,),
        ).fetchone()
        old_bbox = dict(old_row) if old_row else None
        width = normalized["max_x"] - normalized["min_x"]
        height = normalized["max_y"] - normalized["min_y"]
        GeometryRepository(self.connection).upsert(
            object_id,
            GeometryInput(
                center_x=normalized["min_x"] + width / 2,
                center_y=normalized["min_y"] + height / 2,
                width=width,
                height=height,
                min_x=normalized["min_x"],
                min_y=normalized["min_y"],
                max_x=normalized["max_x"],
                max_y=normalized["max_y"],
            ),
        )
        self.connection.execute(
            "UPDATE cad_object SET status = 'corrected', updated_at = datetime('now') WHERE id = ?",
            (object_id,),
        )
        self.corrections.add(
            entity_type="geometry",
            entity_id=object_id,
            field_name="bbox",
            old_value=old_bbox,
            new_value=normalized,
            operator=operator,
            reason=reason,
        )
        return {"object_id": object_id, "field": "bbox", "old_value": old_bbox, "new_value": normalized}

    def _object(self, object_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM cad_object WHERE id = ?", (object_id,)).fetchone()
        if not row:
            raise ValueError(f"cad_object not found: {object_id}")
        return dict(row)


class RecognitionEvaluationService:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def evaluate_file(
        self,
        path: str | Path,
        iou_threshold: float = 0.5,
        status: str | None = None,
    ) -> dict[str, Any]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return self.evaluate_data(payload, iou_threshold=iou_threshold, status=status)

    def evaluate_data(
        self,
        ground_truth: dict[str, Any],
        iou_threshold: float = 0.5,
        status: str | None = None,
    ) -> dict[str, Any]:
        source_uri = ground_truth.get("source_uri")
        truth = [_truth_object(item) for item in ground_truth.get("objects", [])]
        predictions = self._predictions(source_uri=source_uri, status=status)
        matches: list[dict[str, Any]] = []
        matched_truth: set[int] = set()
        matched_predictions: set[int] = set()

        for pred_index, prediction in enumerate(predictions):
            best: tuple[int, float] | None = None
            for truth_index, item in enumerate(truth):
                if truth_index in matched_truth:
                    continue
                if prediction["class_code"] != item["class_code"]:
                    continue
                score = bbox_iou(prediction["bbox"], item["bbox"])
                if score >= iou_threshold and (best is None or score > best[1]):
                    best = (truth_index, score)
            if best is None:
                continue
            truth_index, score = best
            matched_truth.add(truth_index)
            matched_predictions.add(pred_index)
            matches.append(
                {
                    "ground_truth_id": truth[truth_index]["id"],
                    "hypothesis_id": prediction["id"],
                    "class_code": prediction["class_code"],
                    "iou": score,
                }
            )

        missed = [item for index, item in enumerate(truth) if index not in matched_truth]
        wrong = [item for index, item in enumerate(predictions) if index not in matched_predictions]
        matched = len(matches)
        precision = round(matched / len(predictions), 4) if predictions else 0.0
        recall = round(matched / len(truth), 4) if truth else 0.0
        return {
            "source_uri": source_uri,
            "iou_threshold": iou_threshold,
            "status": status,
            "ground_truth": len(truth),
            "predicted": len(predictions),
            "matched": matched,
            "false_positive": len(wrong),
            "false_negative": len(missed),
            "precision": precision,
            "recall": recall,
            "by_class": _by_class(truth, predictions, matches),
            "matches": matches,
            "missed": missed,
            "wrong": wrong,
        }

    def _predictions(self, source_uri: str | None, status: str | None) -> list[dict[str, Any]]:
        conditions = []
        params: list[Any] = []
        if source_uri:
            conditions.append("s.source_uri = ?")
            params.append(source_uri)
        if status:
            conditions.append("h.status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"""
            SELECT h.id, h.class_code, h.bbox_json, h.status, s.source_uri
            FROM object_hypothesis h
            JOIN source_document s ON s.id = h.source_document_id
            {where}
            ORDER BY h.source_document_id, h.source_local_id, h.id
            """,
            params,
        ).fetchall()
        predictions = []
        for row in rows:
            bbox = normalize_bbox(json.loads(row["bbox_json"]) if row["bbox_json"] else None)
            if not bbox:
                continue
            predictions.append(
                {
                    "id": row["id"],
                    "class_code": row["class_code"],
                    "bbox": bbox,
                    "status": row["status"],
                    "source_uri": row["source_uri"],
                }
            )
        return predictions


def _truth_object(item: dict[str, Any]) -> dict[str, Any]:
    bbox = normalize_bbox(item.get("bbox"))
    if not bbox:
        raise ValueError(f"ground truth object has invalid bbox: {item.get('id')}")
    return {
        "id": item.get("id"),
        "class_code": item["class_code"],
        "bbox": bbox,
        "attributes": item.get("attributes", {}),
    }


def _by_class(
    truth: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    matches: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    class_codes = sorted(
        {item["class_code"] for item in truth}
        | {item["class_code"] for item in predictions}
        | {item["class_code"] for item in matches}
    )
    result = {}
    for class_code in class_codes:
        gt_count = sum(1 for item in truth if item["class_code"] == class_code)
        pred_count = sum(1 for item in predictions if item["class_code"] == class_code)
        match_count = sum(1 for item in matches if item["class_code"] == class_code)
        result[class_code] = {
            "ground_truth": gt_count,
            "predicted": pred_count,
            "matched": match_count,
            "false_positive": pred_count - match_count,
            "false_negative": gt_count - match_count,
            "precision": round(match_count / pred_count, 4) if pred_count else 0.0,
            "recall": round(match_count / gt_count, 4) if gt_count else 0.0,
        }
    return result
