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
- `RuleTemplateSeeder` for idempotent rule template seeding from JSON.
- Candidate review CLI commands for listing, accepting, and rejecting relation candidates.
- Strict taxonomy mode for production-like imports.
- CLI commands: `init-db`, `seed-taxonomy`, `import-json`, `seed-rules`, `seed-demo`, `list-objects`, `nearest`, `infer-relations`, `list-candidates`, `accept-candidate`, `reject-candidate`, `export-csv`.
- Cleanroom CAD taxonomy JSON v0.2.0 with 164 object classes.
- Test coverage for import, taxonomy, rule seeding, candidate review, integration, taxonomy structure, and baseline relation flow.

Milestone 1 and Milestone 2 are complete. The current system can import normalized parser output, validate classes against taxonomy, seed rules, infer one demo relation, review relation candidates, and export CSV.

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

Lesson:

Object import is only the first half of the engineering data foundation. Relation inference requires rule templates or another candidate-producing service.

## Milestone 2: Rule And Candidate Workflow

Status: COMPLETE.

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

Completed:

- Rule template JSON format.
- `seed-rules --input samples/demo_rules.json`.
- Strict taxonomy mode for `import-json`.
- Candidate review CLI commands:
  - `list-candidates`
  - `accept-candidate <candidate_id>`
  - `reject-candidate <candidate_id>`
- README workflow that produces a real relation.
- Demo sample aligned with the current taxonomy using `DDC -> CONTROL_PANEL`.
- Tests for rule seeding, strict taxonomy, candidate review, and end-to-end inference.

Acceptance flow:

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

## Milestone 3: Multi-Discipline Taxonomy Profile Foundation

Status: COMPLETE.

Detailed task package:

```text
docs/agent_tasks_round_3.md
```

Goal:

```text
multi-discipline taxonomy profile
  -> expected attributes
  -> relation hints
  -> budget profile hints
  -> installation profile hints
  -> validation tests
```

Completed:

- Renamed the primary taxonomy to `dwg_rec_system/taxonomy/cad_object_taxonomy.json`.
- Added the engineering profile overlay `dwg_rec_system/taxonomy/engineering_class_profiles.json`.
- Covered the first practical profile groups:
  - HVAC
  - PIPING
  - ELEC
  - BMS
  - CLEANROOM
- Defined profile entries that reference existing base taxonomy codes.
- Added validation tests for profile shape, required profile groups, class code uniqueness, base taxonomy code references, quantity methods, and installation defaults.
- Confirmed the engineering profile is not seeded into `object_class`.
- Added `docs/taxonomy_profile.md`.

Reason:

Quantity takeoff, budgeting, and installation planning need a shared engineering dictionary before durable quantity or budget tables are added.

## Milestone 4: Quantity Takeoff

Status: NEXT.

Goal:

```text
cad_object + geometry + attribute + relation + taxonomy profile
  -> quantity_item
  -> quantity export
```

Candidate work:

- Add a `quantity_item` table through an explicit architecture task.
- Add `services/quantity.py`.
- Generate quantity rows from objects, geometry, attributes, and relations.
- Support count, length, area, grouped count, and formula-driven quantity methods.
- Export quantity CSV.

Success criteria:

- Imported objects can produce auditable quantity rows.
- Quantity evidence records the source object, method, grouping key, and confidence.
- Tests cover count, length, area, and grouped quantities.

## Milestone 5: Budgeting

Status: PLANNED.

Goal:

```text
cad_object + attribute + geometry + relation + quantity_item
  -> data quality findings
  -> review priorities
```

Candidate work:

- Add data quality checks before budgeting.
- Detect missing required attributes from `engineering_class_profiles.json`.
- Detect missing geometry needed for quantity methods.
- Detect low confidence objects.
- Detect missing accepted relations that are important for installation or budgeting.
- Produce reviewable findings without blocking deterministic workflows.

Success criteria:

- The system can report which objects or quantities need human review.
- Budgeting can avoid pretending uncertain input is exact.
- Findings preserve evidence and object references.

## Milestone 6: Budgeting

Status: PLANNED.

Goal:

```text
quantity_item
  -> cost_item match
  -> budget_item
  -> budget export
```

Candidate work:

- Add `cost_item` and `budget_item` through an explicit architecture task.
- Add `services/budget.py`.
- Add sample cost item JSON.
- Match quantity items to cost items by class, discipline, unit, and spec hints.
- Export budget CSV or Excel.

Success criteria:

- Quantity items can become budget items.
- Budget totals can be grouped by project, drawing, discipline, system, and area.
- Budget records remain auditable and do not overwrite quantity records.

## Milestone 7: Installation Guidance

Status: PLANNED.

Goal:

```text
cad_object + relation + taxonomy installation profile
  -> install_task
  -> install_dependency
  -> install_instruction
```

Candidate work:

- Add installation template and task tables through an explicit architecture task.
- Add `services/installation.py`.
- Generate object-level installation tasks from taxonomy profiles.
- Generate simple dependencies from accepted relations.
- Generate readable installation instructions.

Success criteria:

- Object classes can produce installation tasks.
- Relations can produce dependency hints.
- Installation instructions cite source objects and relation evidence.

## Milestone 8: Recognition Modeling Layer

Status: PLANNED.

Goal:

```text
PDF/DWG/DXF/image source
  -> primitives
  -> recognition candidates
  -> object hypotheses
  -> accepted hypothesis
  -> ObjectStore
```

Candidate work:

- Design source document, page/layout, primitive, candidate, and hypothesis tables.
- Preserve evidence from PDF vectors, text, OCR, CAD metadata, geometry, and model outputs.
- Define status flow for hypotheses: pending, accepted, rejected, merged, superseded.
- Define deterministic source-local ids for PDF objects that do not have CAD handles.
- Ensure accepted hypotheses enter the existing normalized JSON / ObjectStore boundary.

Success criteria:

- Recognition output is reviewable before becoming final objects.
- Accepted objects are traceable back to recognition evidence.
- Parser/model output does not write directly to `cad_object`.

## Milestone 9: Parser Adapter Layer

Status: PLANNED.

Goal:

Connect real CAD parsing output without changing the object store contract.

Candidate work:

- Add parser adapter interfaces under `dwg_rec_system/importers/`, `dwg_rec_system/parsers/`, or a future recognition package.
- Support DXF first if DWG tooling is unavailable locally.
- Support PDF primitive extraction after recognition modeling boundaries are defined.
- Convert block, text, line, polyline, and bbox records into normalized JSON.
- Preserve parser metadata in `cad_meta.raw_meta` or import job stats.

Success criteria:

- A real or representative parsed file imports through the same `import-json` path.
- No parser-specific code leaks into `ObjectStore`.

## Milestone 10: Stronger Rule Inference

Status: PLANNED.

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

## Milestone 11: Review And Correction Workflow

Status: PLANNED.

Goal:

Make uncertain inference and manual correction operational.

Candidate work:

- CLI/API commands for manual relation correction.
- Tests for correction log behavior.
- Artifact records for generated files.

Success criteria:

- Manual correction marks old relation state and creates audit records.
- Candidate review and manual correction can be performed without direct SQL.

## Milestone 12: API Layer

Status: PLANNED.

Goal:

Expose the object store and inference workflows to UI, CAD plugins, and LLM services.

Candidate work:

- Add FastAPI or similar only after dependency decision.
- Endpoints for import, list objects, object detail, candidates, relations, quantity, budget, installation plan, and export.
- Keep CLI behavior working.

Success criteria:

- API calls use the same service layer as CLI.
- No duplicate import, inference, quantity, budget, or installation logic.

## Milestone 13: Local LLM Inference Layer

Status: PLANNED.

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

## Milestone 14: Production Database Path

Status: PLANNED.

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

Do Round 4 next.

Round 4 should implement quantity takeoff on top of the existing `quantity_item` schema. Do not start budget tables, installation tables, real DWG/DXF/PDF parsing, API, LLM, or PostGIS implementation until quantity item semantics are implemented and tested.
