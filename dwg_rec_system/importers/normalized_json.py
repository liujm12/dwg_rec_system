from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import CadMetaInput, GeometryInput, ObjectInput
from ..repositories import (
    DrawingRepository,
    ObjectClassRepository,
    ProjectRepository,
)
from ..services.object_store import ObjectStore


class NormalizedJsonImporter:
    """Import normalized CAD parser JSON into ObjectStore.

    Follows the protocol defined in docs/import_format.md.
    """

    def __init__(self, connection):
        self.connection = connection
        self.store = ObjectStore(connection)
        self.projects = ProjectRepository(connection)
        self.drawings = DrawingRepository(connection)
        self.classes = ObjectClassRepository(connection)

    def import_file(self, path: str | Path) -> dict[str, Any]:
        raw = Path(path).read_text(encoding="utf-8")
        payload = json.loads(raw)
        return self.import_data(payload)

    def import_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        # ------------------------------------------------------------------
        # Validate required top-level shape
        # ------------------------------------------------------------------
        if "objects" not in payload:
            raise ValueError("missing 'objects' in import payload")
        if not isinstance(payload["objects"], list):
            raise ValueError("'objects' must be a list")

        objects_list = payload["objects"]

        # ------------------------------------------------------------------
        # Resolve project
        # ------------------------------------------------------------------
        project_id: str | None = None
        project_section = payload.get("project")
        if project_section:
            project_id = self.projects.get_or_create(
                code=project_section.get("code", "IMPORT"),
                name=project_section.get("name", "Imported Project"),
                owner=project_section.get("owner"),
                description=project_section.get("description"),
            )

        # ------------------------------------------------------------------
        # Resolve drawing
        # ------------------------------------------------------------------
        drawing_id: str | None = None
        drawing_source_file: str | None = None
        drawing_section = payload.get("drawing")
        if drawing_section:
            drawing_id = self.drawings.get_or_create(
                drawing_no=drawing_section.get("drawing_no", "IMPORT-001"),
                revision=drawing_section.get("revision"),
                discipline=drawing_section.get("discipline"),
                sheet=drawing_section.get("sheet"),
                title=drawing_section.get("title"),
                source_file=drawing_section.get("source_file"),
                project_id=project_id,
            )
            drawing_source_file = drawing_section.get("source_file")

        # ------------------------------------------------------------------
        # Import each object
        # ------------------------------------------------------------------
        created_count = 0
        updated_count = 0
        errors: list[dict[str, Any]] = []

        for idx, obj_data in enumerate(objects_list):
            try:
                class_name = obj_data.get("class_name")
                if not class_name:
                    raise ValueError(f"object[{idx}]: missing 'class_name'")

                # source_file resolution: object-level wins, then drawing-level
                source_file = obj_data.get("source_file") or drawing_source_file
                if not source_file:
                    raise ValueError(
                        f"object[{idx}]: missing 'source_file' (no object-level or drawing-level value)"
                    )

                handle = obj_data.get("handle")
                if not handle:
                    raise ValueError(
                        f"object[{idx}]: missing 'handle' — repeatable imports require a stable identity"
                    )

                # Resolve class_id from taxonomy if available
                class_id = self._resolve_class_id(class_name)

                # Build geometry input
                geometry = self._build_geometry(obj_data.get("geometry"))

                # Build CAD metadata input
                cad_meta = self._build_cad_meta(obj_data.get("cad_meta"))

                # Build attributes map
                attributes = obj_data.get("attributes") or {}

                # Determine if this is a create or update
                existing_id = self.store.objects.find_by_source_handle(
                    source_file, handle
                )
                is_update = existing_id is not None

                object_input = ObjectInput(
                    class_name=class_name,
                    subtype=obj_data.get("subtype"),
                    source_file=source_file,
                    handle=handle,
                    drawing_id=drawing_id,
                    class_id=class_id,
                    confidence=float(obj_data.get("confidence", 1.0)),
                    status=obj_data.get("status", "auto"),
                    parser_name=obj_data.get("parser_name"),
                    parser_version=obj_data.get("parser_version"),
                    recognition_model=obj_data.get("recognition_model"),
                    recognition_version=obj_data.get("recognition_version"),
                    geometry=geometry,
                    cad_meta=cad_meta,
                    attributes=attributes,
                )

                self.store.create_object(object_input)

                if is_update:
                    updated_count += 1
                else:
                    created_count += 1

            except Exception as exc:
                errors.append(
                    {"index": idx, "handle": obj_data.get("handle"), "error": str(exc)}
                )

        return {
            "project_id": project_id,
            "drawing_id": drawing_id,
            "objects_total": len(objects_list),
            "created": created_count,
            "updated": updated_count,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_class_id(self, class_name: str) -> str | None:
        """Find object_class by code, return its id or None."""
        try:
            return self.classes.get_or_create(code=class_name, name=class_name)
        except Exception:
            return None

    @staticmethod
    def _build_geometry(raw: dict[str, Any] | None) -> GeometryInput | None:
        if not raw:
            return None
        return GeometryInput(
            center_x=_float_or_none(raw.get("center_x")),
            center_y=_float_or_none(raw.get("center_y")),
            width=_float_or_none(raw.get("width")),
            height=_float_or_none(raw.get("height")),
            rotation=float(raw.get("rotation", 0)),
            min_x=_float_or_none(raw.get("min_x")),
            min_y=_float_or_none(raw.get("min_y")),
            max_x=_float_or_none(raw.get("max_x")),
            max_y=_float_or_none(raw.get("max_y")),
            geometry_type=raw.get("geometry_type", "bbox"),
            geometry_wkt=raw.get("geometry_wkt"),
            geometry_srid=int(raw.get("geometry_srid", 0)),
            raw_geometry=raw.get("raw_geometry"),
        )

    @staticmethod
    def _build_cad_meta(raw: dict[str, Any] | None) -> CadMetaInput | None:
        if not raw:
            return None
        return CadMetaInput(
            layer=raw.get("layer"),
            block_name=raw.get("block_name"),
            color=str(raw["color"]) if "color" in raw else None,
            linetype=raw.get("linetype"),
            owner_block=raw.get("owner_block"),
            raw_meta=raw.get("raw_meta"),
        )


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
