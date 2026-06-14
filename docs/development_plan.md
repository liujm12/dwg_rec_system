# Development Plan

This plan gives Claude Code and DeepSeek sub-agents a staged path for developing the CAD recognition system without losing the current architecture.

## Current State

The project currently has:

- SQLite schema for project, drawing, objects, geometry, CAD metadata, attributes, relations, candidates, corrections, artifacts, and axis tables.
- `ObjectStore` for object ingestion and idempotent create/update by `source_file + handle`.
- `SpatialIndex` for nearest, contains, and overlap queries.
- `RelationEngine` for simple rule-based relation inference through `relation_candidate -> accept -> relation`.
- `NormalizedJsonImporter` for standardized parser-output JSON import.
- `TaxonomySeeder` for idempotent taxonomy seeding.
- CLI commands: `init-db`, `seed-taxonomy`, `import-json`, `seed-demo`, `list-objects`, `nearest`, `infer-relations`, `export-csv`.
- Cleanroom CAD taxonomy JSON v0.2.0 with 164 object classes.
- Test coverage for import, taxonomy, integration, taxonomy structure, and baseline relation flow.

Milestone 1 is complete. The normalized import path works end to end.

## Milestone 1: Normalized Import Foundation

Status: COMPLETE.

Goal:

```text
external CAD parser result JSON -> ObjectStore -> query/export
```

Completed:

- Normalized JSON import format.
- `import-json` CLI.
- Sample parsed CAD JSON.
- Import tests.
- Taxonomy seeding into `object_class`.
- README and import-format documentation.

Remaining lesson:

`import-json -> infer-relations` does not produce relations unless rules have also been seeded. Round 2 addresses this.

## Milestone 2: Rule And Candidate Workflow

Status: NEXT.

Detailed task package:

```text
docs/agent_tasks_round_2.md
```

Goal:

```text
seed-taxonomy
  -> import-json
  -> seed-rules
  -> infer-relations
  -> list/review candidates
  -> export-csv
```

Required work:

- Add rule template JSON format.
- Add `seed-rules --input samples/demo_rules.json`.
- Add strict taxonomy mode for `import-json`.
- Add candidate review CLI commands.
- Update README so the documented workflow produces a real relation.

Success criteria:

```powershell
python -m pytest -q
$env:DWG_REC_DB="data/round2_acceptance.db"
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json --strict-taxonomy
python -m dwg_rec_system.cli seed-rules --input samples/demo_rules.json
python -m dwg_rec_system.cli infer-relations
python -m dwg_rec_system.cli list-candidates
python -m dwg_rec_system.cli export-csv
```

Expected result:

- taxonomy seeding imports 164 object classes
- JSON import creates 2 objects
- repeated JSON import updates the same 2 objects
- rule seeding is idempotent
- relation inference produces a `mounted_on` relation
- candidate listing shows the accepted rule candidate

## Milestone 3: Parser Adapter Layer

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

## Milestone 4: Stronger Rule Inference

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

## Milestone 5: Review And Correction Workflow

Goal:

Make uncertain inference and manual correction operational.

Candidate work:

- CLI/API commands for manual relation correction.
- Tests for correction log behavior.
- Artifact records for generated files.

Success criteria:

- Manual correction marks old relation state and creates audit records.
- Candidate review and manual correction can be performed without direct SQL.

## Milestone 6: API Layer

Goal:

Expose the object store and inference workflows to UI, CAD plugins, and LLM services.

Candidate work:

- Add FastAPI or similar only after dependency decision.
- Endpoints for import, list objects, object detail, candidates, relations, export.
- Keep CLI behavior working.

Success criteria:

- API calls use the same service layer as CLI.
- No duplicate import or inference logic.

## Milestone 7: Local LLM Inference Layer

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

## Milestone 8: Production Database Path

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

Do Round 2 next. Do not start real DWG/DXF parsing, API, LLM, or PostGIS implementation until the rule and candidate workflow is usable from CLI.

