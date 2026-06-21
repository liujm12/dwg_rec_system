from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SUPPORTED_PRIMITIVE_TYPES = {
    "line",
    "polyline",
    "path",
    "rect",
    "circle",
    "arc",
    "text",
    "image",
    "block",
    "symbol",
    "unknown",
}


class SampleJsonParserAdapter:
    adapter_name = "sample-json"
    parser_name = "sample_json_adapter"
    parser_version = "0.1"
    source_type = "json"

    def parse_file(self, path: str | Path) -> dict[str, Any]:
        source_path = Path(path)
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        return self.parse_data(payload, source_uri=str(source_path))

    def parse_data(self, payload: dict[str, Any], source_uri: str | None = None) -> dict[str, Any]:
        source = payload.get("source") or {}
        uri = source.get("uri") or source_uri
        if not uri:
            raise ValueError("sample parser payload requires source.uri or source_uri")
        pages = payload.get("pages")
        if not isinstance(pages, list):
            raise ValueError("sample parser payload requires pages list")

        recognition_payload = {
            "source_document": {
                "source_uri": uri,
                "source_type": source.get("type", self.source_type),
                "title": source.get("title"),
                "parser_name": self.parser_name,
                "parser_version": self.parser_version,
                "metadata": {
                    "adapter_name": self.adapter_name,
                    "raw_source": source,
                },
            },
            "pages": [],
        }

        for page_index, page in enumerate(pages, start=1):
            page_key = _page_key(page, page_index)
            entities = page.get("entities") or []
            detections = page.get("detections") or []
            primitives = [
                self._primitive(entity, page_key, entity_index)
                for entity_index, entity in enumerate(entities, start=1)
            ]
            entity_local_ids = {primitive["source_local_id"] for primitive in primitives}
            candidates = [
                self._candidate(detection, page_key, detection_index, entity_local_ids)
                for detection_index, detection in enumerate(detections, start=1)
            ]
            hypotheses = [
                self._hypothesis(detection, page_key, detection_index)
                for detection_index, detection in enumerate(detections, start=1)
            ]
            recognition_payload["pages"].append(
                {
                    "page": {
                        "page_no": page.get("page_no"),
                        "layout_name": page.get("layout_name"),
                        "width": page.get("width"),
                        "height": page.get("height"),
                        "unit": page.get("unit"),
                        "scale": page.get("scale"),
                        "rotation": page.get("rotation", 0),
                        "metadata": {
                            "raw_page": {
                                key: value
                                for key, value in page.items()
                                if key not in {"entities", "detections"}
                            }
                        },
                    },
                    "primitives": primitives,
                    "candidates": candidates,
                    "hypotheses": hypotheses,
                }
            )
        return recognition_payload

    def _primitive(self, entity: dict[str, Any], page_key: str, index: int) -> dict[str, Any]:
        primitive_type = entity.get("type") or entity.get("primitive_type") or "unknown"
        if primitive_type not in SUPPORTED_PRIMITIVE_TYPES:
            primitive_type = "unknown"
        local_id = entity.get("id") or entity.get("source_local_id") or _stable_id(
            "ent",
            page_key,
            index,
            primitive_type,
            entity.get("bbox"),
            entity.get("text"),
        )
        return {
            "source_local_id": local_id,
            "primitive_type": primitive_type,
            "geometry": entity.get("geometry"),
            "bbox": entity.get("bbox"),
            "text": entity.get("text"),
            "style": entity.get("style"),
            "raw": entity,
            "confidence": entity.get("confidence", 1.0),
        }

    def _candidate(
        self,
        detection: dict[str, Any],
        page_key: str,
        index: int,
        entity_local_ids: set[str],
    ) -> dict[str, Any]:
        local_id = detection.get("id") or detection.get("source_local_id") or _stable_id(
            "det",
            page_key,
            index,
            detection.get("class_code"),
            detection.get("bbox"),
            detection.get("label"),
        )
        links = []
        for entity_id in detection.get("entity_ids", []):
            if entity_id not in entity_local_ids:
                continue
            links.append(
                {
                    "primitive_source_local_id": entity_id,
                    "role": "geometry",
                    "weight": 1.0,
                    "evidence": {"source": "sample_json.entity_ids"},
                }
            )
        return {
            "source_local_id": local_id,
            "candidate_type": detection.get("candidate_type", "object"),
            "class_code": detection.get("class_code"),
            "label": detection.get("label"),
            "confidence": detection.get("confidence", 1.0),
            "source": detection.get("source", "parser"),
            "model_name": self.parser_name,
            "model_version": self.parser_version,
            "geometry": detection.get("geometry"),
            "bbox": detection.get("bbox"),
            "attributes": detection.get("attributes"),
            "evidence": {
                "adapter_name": self.adapter_name,
                "raw_detection": detection,
                "missing_entity_ids": [
                    entity_id
                    for entity_id in detection.get("entity_ids", [])
                    if entity_id not in entity_local_ids
                ],
            },
            "primitive_links": links,
        }

    def _hypothesis(self, detection: dict[str, Any], page_key: str, index: int) -> dict[str, Any]:
        candidate_id = detection.get("id") or detection.get("source_local_id") or _stable_id(
            "det",
            page_key,
            index,
            detection.get("class_code"),
            detection.get("bbox"),
            detection.get("label"),
        )
        local_id = detection.get("hypothesis_id") or f"hyp-{candidate_id}"
        return {
            "source_local_id": local_id,
            "class_code": detection.get("class_code") or "UNKNOWN",
            "subtype": detection.get("subtype"),
            "confidence": detection.get("confidence", 1.0),
            "geometry": detection.get("geometry"),
            "bbox": detection.get("bbox"),
            "attributes": detection.get("attributes"),
            "evidence": {
                "adapter_name": self.adapter_name,
                "raw_detection": detection,
            },
            "candidate_links": [
                {
                    "candidate_source_local_id": candidate_id,
                    "role": "primary",
                    "weight": 1.0,
                }
            ],
        }


def _page_key(page: dict[str, Any], page_index: int) -> str:
    return str(page.get("layout_name") or page.get("page_no") or page_index)


def _stable_id(prefix: str, page_key: str, index: int, *parts: Any) -> str:
    normalized = "-".join(_normalize_part(part) for part in parts if part is not None)
    return f"{prefix}-{page_key}-{index}-{normalized or 'item'}"


def _normalize_part(value: Any) -> str:
    if isinstance(value, dict):
        value = json.dumps(value, sort_keys=True, separators=(",", ":"))
    text = str(value).strip().lower()
    safe = []
    for char in text:
        if char.isalnum():
            safe.append(char)
        elif char in {"-", "_"}:
            safe.append(char)
        else:
            safe.append("_")
    return "".join(safe).strip("_")[:80]
