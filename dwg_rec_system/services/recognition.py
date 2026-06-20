from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..models import GeometryInput, ObjectInput
from ..repositories import (
    DrawingPageRepository,
    DrawingPrimitiveRepository,
    HypothesisToObjectRepository,
    ObjectClassRepository,
    ObjectHypothesisRepository,
    RecognitionCandidateRepository,
    SourceDocumentRepository,
)
from .object_store import ObjectStore


class RecognitionImportService:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.sources = SourceDocumentRepository(connection)
        self.pages = DrawingPageRepository(connection)
        self.primitives = DrawingPrimitiveRepository(connection)
        self.candidates = RecognitionCandidateRepository(connection)
        self.hypotheses = ObjectHypothesisRepository(connection)

    def import_file(self, path: str | Path) -> dict[str, Any]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return self.import_data(payload)

    def import_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_payload = payload.get("source_document") or {}
        if not source_payload.get("source_uri"):
            raise ValueError("source_document.source_uri is required")
        source_document_id = self.sources.upsert(
            source_uri=source_payload["source_uri"],
            source_type=source_payload.get("source_type", "unknown"),
            project_id=source_payload.get("project_id"),
            file_hash=source_payload.get("file_hash"),
            title=source_payload.get("title"),
            parser_name=source_payload.get("parser_name"),
            parser_version=source_payload.get("parser_version"),
            metadata=source_payload.get("metadata"),
            status=source_payload.get("status", "active"),
        )
        summary = {
            "source_document_id": source_document_id,
            "pages_created": 0,
            "primitives_created": 0,
            "candidates_created": 0,
            "candidate_primitive_links": 0,
            "hypotheses_created": 0,
            "hypothesis_candidate_links": 0,
            "page_ids": [],
            "candidate_ids": [],
            "hypothesis_ids": [],
        }

        for page_index, page_item in enumerate(payload.get("pages", []), start=1):
            page_payload = page_item.get("page") or {}
            page_id = self.pages.upsert(
                source_document_id=source_document_id,
                drawing_id=page_payload.get("drawing_id"),
                page_no=page_payload.get("page_no", page_index),
                layout_name=page_payload.get("layout_name"),
                width=page_payload.get("width"),
                height=page_payload.get("height"),
                unit=page_payload.get("unit"),
                scale=page_payload.get("scale"),
                rotation=page_payload.get("rotation", 0),
                metadata=page_payload.get("metadata"),
            )
            summary["pages_created"] += 1
            summary["page_ids"].append(page_id)

            primitive_ids_by_local: dict[str, str] = {}
            for primitive_index, primitive in enumerate(page_item.get("primitives", []), start=1):
                local_id = primitive.get("source_local_id") or f"prim-{primitive_index}"
                primitive_id = self.primitives.upsert(
                    page_id=page_id,
                    source_local_id=local_id,
                    primitive_type=primitive.get("primitive_type", "unknown"),
                    geometry=primitive.get("geometry"),
                    bbox=primitive.get("bbox"),
                    text=primitive.get("text"),
                    style=primitive.get("style"),
                    raw=primitive.get("raw"),
                    confidence=primitive.get("confidence", 1.0),
                )
                primitive_ids_by_local[local_id] = primitive_id
                summary["primitives_created"] += 1

            candidate_ids_by_local: dict[str, str] = {}
            for candidate_index, candidate in enumerate(page_item.get("candidates", []), start=1):
                local_id = candidate.get("source_local_id") or f"cand-{candidate_index}"
                candidate_id = self.candidates.upsert(
                    page_id=page_id,
                    source_local_id=local_id,
                    candidate_type=candidate.get("candidate_type", "unknown"),
                    class_code=candidate.get("class_code"),
                    label=candidate.get("label"),
                    confidence=candidate.get("confidence", 1.0),
                    source=candidate.get("source", "import"),
                    model_name=candidate.get("model_name"),
                    model_version=candidate.get("model_version"),
                    geometry=candidate.get("geometry"),
                    bbox=candidate.get("bbox"),
                    attributes=candidate.get("attributes"),
                    evidence=candidate.get("evidence"),
                    status=candidate.get("status", "pending"),
                )
                candidate_ids_by_local[local_id] = candidate_id
                summary["candidate_ids"].append(candidate_id)
                summary["candidates_created"] += 1
                for link in candidate.get("primitive_links", []):
                    primitive_id = primitive_ids_by_local.get(link["primitive_source_local_id"])
                    if not primitive_id:
                        continue
                    self.candidates.link_primitive(
                        candidate_id=candidate_id,
                        primitive_id=primitive_id,
                        role=link.get("role", "context"),
                        weight=link.get("weight", 1.0),
                        evidence=link.get("evidence"),
                    )
                    summary["candidate_primitive_links"] += 1

            for hypothesis_index, hypothesis in enumerate(page_item.get("hypotheses", []), start=1):
                local_id = hypothesis.get("source_local_id") or f"hyp-{hypothesis_index}"
                hypothesis_id = self.hypotheses.upsert(
                    page_id=page_id,
                    source_document_id=source_document_id,
                    class_code=hypothesis["class_code"],
                    source_local_id=local_id,
                    subtype=hypothesis.get("subtype"),
                    confidence=hypothesis.get("confidence", 1.0),
                    geometry=hypothesis.get("geometry"),
                    bbox=hypothesis.get("bbox"),
                    attributes=hypothesis.get("attributes"),
                    evidence=hypothesis.get("evidence"),
                    status=hypothesis.get("status", "pending"),
                )
                summary["hypothesis_ids"].append(hypothesis_id)
                summary["hypotheses_created"] += 1
                for link in hypothesis.get("candidate_links", []):
                    candidate_id = candidate_ids_by_local.get(link["candidate_source_local_id"])
                    if not candidate_id:
                        continue
                    self.hypotheses.link_candidate(
                        hypothesis_id=hypothesis_id,
                        candidate_id=candidate_id,
                        role=link.get("role", "primary"),
                        weight=link.get("weight", 1.0),
                        evidence=link.get("evidence"),
                    )
                    summary["hypothesis_candidate_links"] += 1

        return summary


class HypothesisAcceptanceService:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.hypotheses = ObjectHypothesisRepository(connection)
        self.mappings = HypothesisToObjectRepository(connection)
        self.candidates = RecognitionCandidateRepository(connection)

    def accept(
        self,
        hypothesis_id: str,
        accepted_by: str | None = None,
        acceptance_method: str = "manual",
    ) -> dict[str, Any]:
        hypothesis = self.hypotheses.get(hypothesis_id)
        if not hypothesis:
            raise ValueError(f"object hypothesis not found: {hypothesis_id}")
        if hypothesis["status"] == "rejected":
            raise ValueError(f"rejected hypothesis cannot be accepted: {hypothesis_id}")
        existing = self.mappings.find_by_hypothesis(hypothesis_id)
        if existing:
            return {
                "hypothesis_id": hypothesis_id,
                "object_id": existing["object_id"],
                "mapping_id": existing["id"],
                "already_accepted": True,
            }

        page = DrawingPageRepository(self.connection).get(hypothesis["page_id"])
        source = SourceDocumentRepository(self.connection).get(hypothesis["source_document_id"])
        if not page or not source:
            raise ValueError(f"hypothesis source context is incomplete: {hypothesis_id}")

        class_row = ObjectClassRepository(self.connection).find_by_code(hypothesis["class_code"])
        object_id = ObjectStore(self.connection).create_object(
            ObjectInput(
                class_name=hypothesis["class_code"],
                subtype=hypothesis["subtype"],
                source_file=source["source_uri"],
                handle=_object_handle(page, hypothesis),
                drawing_id=page.get("drawing_id"),
                class_id=class_row["id"] if class_row else None,
                confidence=float(hypothesis["confidence"] or 1.0),
                parser_name=source.get("parser_name"),
                parser_version=source.get("parser_version"),
                recognition_model="recognition_hypothesis",
                recognition_version="0.1",
                geometry=_geometry_input(hypothesis),
                attributes=_json_field(hypothesis.get("attributes_json")),
            )
        )
        mapping_id = self.mappings.create(
            hypothesis_id=hypothesis_id,
            object_id=object_id,
            accepted_by=accepted_by,
            acceptance_method=acceptance_method,
            evidence={
                "source_document_id": source["id"],
                "page_id": page["id"],
                "source_local_id": hypothesis["source_local_id"],
            },
        )
        self.hypotheses.update_status(hypothesis_id, "accepted")
        for candidate_id in self.candidates.linked_candidate_ids(hypothesis_id):
            self.candidates.update_status(candidate_id, "accepted")
        return {
            "hypothesis_id": hypothesis_id,
            "object_id": object_id,
            "mapping_id": mapping_id,
            "already_accepted": False,
        }


def _json_field(value: str | None) -> dict[str, Any]:
    return json.loads(value) if value else {}


def _geometry_input(hypothesis: dict[str, Any]) -> GeometryInput | None:
    raw_geometry = _json_field(hypothesis.get("geometry_json"))
    bbox = _json_field(hypothesis.get("bbox_json"))
    if not raw_geometry and not bbox:
        return None
    min_x = bbox.get("min_x")
    min_y = bbox.get("min_y")
    max_x = bbox.get("max_x")
    max_y = bbox.get("max_y")
    width = None
    height = None
    center_x = None
    center_y = None
    if None not in (min_x, min_y, max_x, max_y):
        width = float(max_x) - float(min_x)
        height = float(max_y) - float(min_y)
        center_x = float(min_x) + width / 2
        center_y = float(min_y) + height / 2
    return GeometryInput(
        center_x=center_x,
        center_y=center_y,
        width=width,
        height=height,
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
        raw_geometry=raw_geometry or None,
    )


def _object_handle(page: dict[str, Any], hypothesis: dict[str, Any]) -> str:
    page_key = page.get("layout_name") or page.get("page_no") or page["id"]
    return f"{page_key}:{hypothesis['source_local_id']}"
