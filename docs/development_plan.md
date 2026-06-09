# Development Plan

This plan gives Claude Code and DeepSeek sub-agents a staged path for developing the CAD recognition system without losing the current architecture.

## Current State

The project currently has:

- SQLite schema for project, drawing, objects, geometry, CAD metadata, attributes, relations, candidates, corrections, artifacts, and axis tables.
- `ObjectStore` for object ingestion.
- `SpatialIndex` for nearest, contains, and overlap queries.
- `RelationEngine` for simple rule-based relation inference.
- CLI commands for initialization, demo seeding, listing, inference, and CSV export.
- A cleanroom CAD taxonomy JSON file.
- Baseline pytest coverage for object, spatial, and relation flow.

The missing production-enabling path is:

```text
real parser output -> normalized import -> object store
```

## Milestone 1: Normalized Import Foundation

Goal:

```text
external CAD parser result JSON -> ObjectStore -> query/infer/export
```

Required work:

- Define normalized JSON import format.
- Implement `import-json` CLI.
- Add sample parsed CAD JSON.
- Add tests for import behavior.
- Seed taxonomy into `object_class`.
- Document import commands and expectations.

Success criteria:

```powershell
python -m pytest -q
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json
python -m dwg_rec_system.cli list-objects
python -m dwg_rec_system.cli infer-relations
python -m dwg_rec_system.cli export-csv
```

## Milestone 2: Parser Adapter Layer

Goal:

Connect real CAD parsing output without changing the object store contract.

Candidate work:

- Add parser adapter interfaces under `dwg_rec_system/importers/` or `dwg_rec_system/parsers/`.
- Support DXF first if DWG tooling is unavailable locally.
- Convert block, text, line, polyline, and bbox records into normalized JSON.
- Preserve parser metadata in `cad_meta.raw_meta` or import job stats.

Success criteria:

- A real or representative parsed file imports through the same `import-json` path.
- No parser-specific code leaks into `ObjectStore`.

## Milestone 3: Stronger Rule Inference

Goal:

Expand relation inference beyond nearest mounted-on rules.

Candidate relation types:

- `contains`
- `located_in`
- `labels`
- `installed_in`
- `installed_on`
- `connected_to`
- `located_on_axis`

Candidate rule strategies:

- bbox containment
- bbox overlap ratio
- nearest text-to-object label binding
- class-compatible relation templates
- layer/block-based confidence hints

Success criteria:

- Rules produce `relation_candidate` records.
- Accepted relations preserve evidence.
- Tests cover each new rule type.

## Milestone 4: Review And Correction Workflow

Goal:

Make uncertain inference and manual correction operational.

Candidate work:

- CLI commands to list, accept, and reject candidates.
- CLI/API commands for manual relation correction.
- Tests for correction log behavior.
- Artifact records for generated files.

Success criteria:

- A candidate can be reviewed without direct SQL.
- Manual correction marks old relation state and creates audit records.

## Milestone 5: API Layer

Goal:

Expose the object store and inference workflows to UI, CAD plugins, and LLM services.

Candidate work:

- Add FastAPI or similar only after dependency decision.
- Endpoints for import, list objects, object detail, candidates, relations, export.
- Keep CLI behavior working.

Success criteria:

- API calls use the same service layer as CLI.
- No duplicate import or inference logic.

## Milestone 6: Local LLM Inference Layer

Goal:

Add replaceable local LLM-assisted inference.

Candidate work:

- Define LLM request/response JSON contract.
- Add a rule-only fallback.
- Add adapters for Ollama or vLLM only when explicitly approved.
- Store LLM suggestions in `relation_candidate`.

Success criteria:

- LLM output never writes directly to `relation`.
- LLM service can be disabled without breaking deterministic workflows.

## Milestone 7: Production Database Path

Goal:

Prepare PostgreSQL/PostGIS deployment while keeping SQLite useful for local development.

Candidate work:

- Add PostgreSQL schema/migration scripts.
- Map WKT/SRID to PostGIS geometry.
- Add spatial indexes.
- Keep import and relation semantics identical.

Success criteria:

- SQLite tests still pass.
- Postgres-specific tests are isolated and optional unless configured.

## Near-Term Priority

Do Milestone 1 first. Do not start UI, API, LLM, or PostGIS implementation before the normalized import path works end to end.

