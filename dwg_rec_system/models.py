from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GeometryInput:
    center_x: float | None = None
    center_y: float | None = None
    width: float | None = None
    height: float | None = None
    rotation: float = 0
    min_x: float | None = None
    min_y: float | None = None
    max_x: float | None = None
    max_y: float | None = None
    geometry_type: str = "bbox"
    geometry_wkt: str | None = None
    geometry_srid: int = 0
    raw_geometry: dict[str, Any] | None = None


@dataclass(frozen=True)
class CadMetaInput:
    layer: str | None = None
    block_name: str | None = None
    color: str | None = None
    linetype: str | None = None
    owner_block: str | None = None
    raw_meta: dict[str, Any] | None = None


@dataclass(frozen=True)
class ObjectInput:
    class_name: str
    subtype: str | None = None
    source_file: str | None = None
    handle: str | None = None
    drawing_id: str | None = None
    import_job_id: str | None = None
    class_id: str | None = None
    confidence: float = 1.0
    status: str = "auto"
    parser_name: str | None = None
    parser_version: str | None = None
    recognition_model: str | None = None
    recognition_version: str | None = None
    geometry: GeometryInput | None = None
    cad_meta: CadMetaInput | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleTemplateInput:
    name: str
    source_class: str
    target_class: str
    relation_type: str
    version: str = "1"
    rule_kind: str = "spatial"
    max_distance: float | None = None
    expression: str | None = None
    min_confidence: float = 0.5
    priority: int = 100
    enabled: bool = True
    config: dict[str, Any] | None = None
    valid_from: str | None = None
    valid_to: str | None = None
