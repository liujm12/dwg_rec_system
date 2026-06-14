# Architecture Notes

This document describes the current system architecture and the design boundaries that implementation agents must preserve.

## System Intent

The repository is the foundation of a CAD/DWG recognition system for engineering drawings. Its job is to store recognized CAD objects, preserve their geometry and raw CAD metadata, infer relations, keep auditability, and support later generation of engineering deliverables.

The system should remain parser-agnostic. A DWG parser, DXF parser, CAD plugin, OCR pipeline, or LLM preprocessing service should all feed the same normalized import path.

## Main Data Flow

```text
CAD/DWG/DXF/parser output
  -> normalized JSON import format
  -> ObjectInput / GeometryInput / CadMetaInput
  -> ObjectStore
  -> cad_object + geometry + cad_meta + attribute
  -> SpatialIndex
  -> RelationEngine / future LLM inference
  -> relation_candidate
  -> accepted relation
  -> exports/artifacts
```

## Core Domain Model

### Object

`cad_object` is the universal entity table. Anything recognized from a drawing can be an object:

- equipment
- rack
- room
- pipe
- cable tray
- valve
- text label
- dimension
- axis
- annotation

Avoid introducing separate first-class tables such as `device`, `rack`, `pipe`, or `valve` unless there is a clear architecture decision. Domain-specific facts should usually be stored in `attribute`.

### Geometry

`geometry` stores position and shape-related data separately from `cad_object`.

Current SQLite prototype fields include:

- center point
- width/height
- rotation
- bbox columns
- WKT/SRID fields reserved for PostGIS migration
- raw geometry JSON

Spatial helper tables `geometry_rtree` and `geometry_rtree_map` are SQLite-specific. Do not design future code around them as permanent domain tables.

### CAD Metadata

`cad_meta` preserves original CAD information:

- layer
- block name
- color
- linetype
- owner block
- raw metadata JSON

This data is important for debugging recognition errors and should not be discarded.

### Attribute

`attribute` is an EAV table for flexible fields such as `tag`, `vendor`, `model`, `diameter`, `room_no`, and `signal_type`.

Use `namespace`, `normalized_value`, `unit`, and `is_inferred` when adding richer import or inference behavior.

### Relation Candidate

`relation_candidate` stores suggestions from rules, LLMs, parsers, or imports.

Examples:

- a rule suggests `DCC mounted_on DCC_RACK`
- an LLM suggests `TEXT_LABEL labels VALVE`
- a parser suggests `CABLE connects PANEL`

Candidate relation records can be accepted, rejected, or superseded. This table is the buffer between uncertain inference and final engineering truth.

### Relation

`relation` stores accepted engineering graph edges. It should not be treated as a scratchpad for raw suggestions.

Accepting a candidate should preserve a link through `candidate_id` when possible.

### Correction And Audit

Human changes should be represented with:

- `manual_relation` for relation-specific corrections
- `correction_log` for general object, relation, attribute, geometry, or drawing corrections

Auditability is a product requirement, not an optional feature.

## Module Responsibilities

### `dwg_rec_system.db`

Owns database connection, session lifecycle, schema initialization, and compatibility migrations for evolving SQLite databases.

### `dwg_rec_system.models`

Owns input dataclasses used by importers and services. Keep these stable and explicit.

### `dwg_rec_system.repositories`

Owns low-level SQL operations. Business workflows should prefer services unless direct repository access is specifically needed.

### `dwg_rec_system.services.object_store`

Owns recognized object ingestion. Importers should call `ObjectStore.create_object()` rather than writing `cad_object`, `geometry`, `cad_meta`, and `attribute` independently.

### `dwg_rec_system.services.spatial_index`

Owns spatial lookup operations such as nearest, contains, and overlap. The current nearest implementation is simple and center-point based; do not assume it is the final PostGIS strategy.

### `dwg_rec_system.services.relation_engine`

Owns rule-based relation inference. It should produce candidates first and then accept them only when current rule semantics say the relation is final.

### `dwg_rec_system.services.exports`

Owns current CSV export behavior. Future BOM, installation table, IO mapping, and schedule outputs should become artifact-aware.

## Import Boundary

The normalized JSON importer is the next priority. It should be a boundary adapter:

```text
external JSON
  -> validation / normalization
  -> repository setup for project/drawing/class
  -> ObjectInput
  -> ObjectStore
```

It should not introduce parser-specific assumptions such as AutoCAD-only handles or layer naming conventions. Those can be optional metadata fields.

## Taxonomy Boundary

`dwg_rec_system/taxonomy/cad_object_taxonomy.json` is the primary CAD object class dictionary. It seeds `object_class` but should not hard-code all domain behavior into Python conditionals.

`dwg_rec_system/taxonomy/engineering_class_profiles.json` is an engineering profile overlay for existing object class codes. It should not create a second taxonomy or seed new `object_class` rows. Later quantity, budget, and installation services can consume it for expected attributes, budget hints, installation hints, and relation hints.

Object class metadata can help importers:

- resolve class IDs
- validate class codes
- attach discipline
- document expected attributes and relation types

Unknown classes should be handled deliberately: either reject with a clear error or import as object records without `class_id`, depending on the importer mode.

## LLM Boundary

LLMs are future inference services, not the system of record.

Correct LLM flow:

```text
structured object context
  -> LLM inference
  -> relation_candidate
  -> review/acceptance
  -> relation
```

Incorrect flow:

```text
raw DWG
  -> LLM
  -> relation
```

LLM outputs must be structured, auditable, and replaceable by rule-only fallback behavior.

## Migration Direction

Current prototype uses SQLite. Future production deployment may use PostgreSQL/PostGIS.

Preserve these migration paths:

- `geometry_wkt + geometry_srid` -> PostGIS geometry
- bbox columns -> generated/cache columns or query fallback
- `relation_candidate` -> inference suggestion table
- `relation` -> accepted graph edge table
- `correction_log` -> audit trail

Do not build new code that depends on SQLite-specific internals unless the task is explicitly SQLite-only.

## Design Constraints For Agents

Agents must report a conflict instead of changing architecture when a task appears to require:

- changing primary tables
- adding columns to core tables
- changing object identity semantics
- bypassing `relation_candidate`
- adding runtime dependencies
- replacing service/repository boundaries
- making broad cross-cutting refactors
