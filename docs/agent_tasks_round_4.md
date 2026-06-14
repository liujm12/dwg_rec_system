# Agent Tasks Round 4

Round 4 turns recognized CAD objects into durable engineering quantity rows.

Round 3 provided:

```text
cad_object_taxonomy.json
  -> object_class

engineering_class_profiles.json
  -> budget.quantity_method
  -> budget.unit
  -> budget.group_by
  -> expected_attributes
```

The schema now includes:

```text
quantity_item
```

Round 4 should make this work:

```text
seed-taxonomy
  -> import-json --strict-taxonomy
  -> generate-quantities
  -> list-quantities
  -> export-quantities-csv
```

## Round Goal

Implement the first quantity takeoff workflow.

The output of Round 4 is not a budget. It is an auditable quantity layer that later budgeting services can consume.

## Coordination Rules

- Every agent must read `CLAUDE.md`, `docs/architecture.md`, `docs/final_roadmap.md`, `docs/taxonomy_profile.md`, and this file.
- Every agent must run `python -m pytest -q`.
- Preserve the existing `quantity_item` schema unless a schema bug is reported explicitly.
- Do not add budget tables or budget services in Round 4.
- Do not add installation tables or installation services in Round 4.
- Do not add external dependencies.
- Do not implement DWG/DXF parsing, API, UI, or LLM behavior.
- Keep object import through `ObjectStore`.
- Keep engineering profiles as configuration, not hard-coded class behavior.

## Quantity Item Contract

`quantity_item` stores durable quantity results.

Core fields:

```text
project_id
drawing_id
source_object_id
class_code
discipline
item_name
spec
unit
quantity
quantity_method
group_key
location
system_code
confidence
source
evidence_json
status
```

Allowed `quantity_method` values:

```text
count_by_object
length_by_geometry
area_by_geometry
grouped_count
formula
manual_review
```

Round 4 should implement only:

```text
count_by_object
grouped_count
length_by_geometry
area_by_geometry
manual_review fallback
```

`formula` should be accepted by schema but not executed until a later round.

## Quantity Semantics

### `count_by_object`

Creates one quantity row per object or per group.

Useful for:

```text
VALVE
PUMP
CONTROL_PANEL
DDC
LIGHT_FIXTURE
PASS_BOX
```

Default quantity:

```text
1
```

### `grouped_count`

Groups objects by configured attribute values from profile `budget.group_by`.

Example:

```text
VALVE|diameter=DN100|material=stainless
```

### `length_by_geometry`

Uses geometry data to estimate length.

Round 4 minimum behavior:

- use `raw_geometry.length` if present
- else use `width` if present
- else use `height` if present
- else create `manual_review` quantity row with evidence explaining the missing length

### `area_by_geometry`

Uses geometry data to estimate area.

Round 4 minimum behavior:

- use `raw_geometry.area` if present
- else use `width * height` if both are present
- else create `manual_review` quantity row with evidence explaining the missing area

### `manual_review`

Creates a quantity row when the profile is valid but the system lacks enough data to calculate a reliable quantity.

Quantity should be:

```text
0
```

Status should be:

```text
auto
```

Evidence should explain why manual review is needed.

## Agent A: Quantity Repository

### Objective

Add repository support for `quantity_item`.

### Allowed Files

- `dwg_rec_system/repositories.py`
- `tests/`

### Disallowed Changes

- Do not modify `schema.sql` unless a schema bug is found and reported.
- Do not add business logic to the repository.
- Do not add external dependencies.

### Required Behavior

Add a repository such as:

```python
class QuantityRepository:
    def upsert(...): ...
    def clear_auto(...): ...
    def list(...): ...
```

Suggested behavior:

- `upsert` should create durable quantity rows.
- `clear_auto` may delete or replace auto-generated rows before regeneration, but must not delete `manual`, `reviewed`, or `corrected` rows.
- `list` should support filters:
  - `project_id`
  - `drawing_id`
  - `class_code`
  - `status`

### Required Tests

Add tests for:

- creating a quantity item
- listing quantity items
- preserving non-auto rows when regenerating

### Validation Commands

```powershell
python -m pytest -q
```

## Agent B: Quantity Service

### Objective

Generate `quantity_item` rows from recognized objects and engineering profiles.

### Allowed Files

- `dwg_rec_system/services/`
- `dwg_rec_system/repositories.py`
- `tests/`
- `docs/` only for clarifying behavior

### Disallowed Changes

- Do not modify `schema.sql` unless a schema bug is found and reported.
- Do not implement budget or installation behavior.
- Do not hard-code class-specific behavior when the engineering profile can provide it.
- Do not add dependencies.

### Required Behavior

Create:

```text
dwg_rec_system/services/quantity.py
```

Suggested API:

```python
class QuantityGenerator:
    def __init__(self, connection, profile_path: str | Path | None = None): ...
    def generate(self, project_id: str | None = None, drawing_id: str | None = None) -> dict: ...
```

The generator should:

- load `engineering_class_profiles.json`
- match `cad_object.class` to profile `code`
- use `budget.quantity_method`
- use `budget.unit`
- use `budget.group_by` to build `spec` and `group_key`
- read object attributes from `attribute`
- read geometry from `geometry`
- create `quantity_item` rows
- include evidence JSON containing:
  - source object id
  - class code
  - quantity method
  - profile group
  - used attributes
  - geometry values used, when applicable
  - reason for manual review, when applicable

Unknown profiles:

- If an object has no engineering profile, skip it by default.
- Count skipped objects in the summary.
- Do not auto-create profiles.

### Required Tests

Add tests for:

- `count_by_object` creates quantity rows
- grouped count uses profile `group_by`
- `length_by_geometry` uses geometry width or raw length
- `area_by_geometry` uses width and height or raw area
- missing geometry creates `manual_review`
- objects without profiles are skipped

### Validation Commands

```powershell
python -m pytest -q
```

## Agent C: Quantity CLI And Export

### Objective

Expose quantity generation and review through CLI.

### Required Commands

```powershell
python -m dwg_rec_system.cli generate-quantities
python -m dwg_rec_system.cli list-quantities
python -m dwg_rec_system.cli export-quantities-csv
```

Optional filters:

```powershell
generate-quantities --project-id <id> --drawing-id <id>
list-quantities --class-code VALVE --status auto
export-quantities-csv --output exports/quantities.csv
```

### Allowed Files

- `dwg_rec_system/cli.py`
- `dwg_rec_system/services/`
- `dwg_rec_system/repositories.py`
- `tests/`
- `README.md`
- `docs/`

### Disallowed Changes

- Do not modify `schema.sql` unless a schema bug is found and reported.
- Do not implement budget export here.
- Do not modify object import behavior.

### Required Behavior

`generate-quantities` should:

- run `QuantityGenerator`
- print JSON summary

`list-quantities` should:

- print quantity rows as JSON
- support class/status filters

`export-quantities-csv` should:

- write quantity rows to CSV
- default to `exports/quantities.csv`
- include enough fields for budget review:
  - class_code
  - discipline
  - item_name
  - spec
  - unit
  - quantity
  - quantity_method
  - group_key
  - status
  - confidence

### Required Tests

Add tests for:

- CLI commands print valid JSON where expected
- CSV export writes expected headers
- command flow works after sample import

### Validation Commands

```powershell
python -m pytest -q
```

## Agent D: Documentation And Acceptance

### Objective

Document the quantity workflow and update the development plan.

### Allowed Files

- `README.md`
- `docs/development_plan.md`
- `docs/final_roadmap.md`
- `docs/agent_tasks_round_4.md`
- `samples/` only if a sample import file needs attributes for quantity examples

### Disallowed Changes

- Do not modify production code.
- Do not modify schema unless a bug is found and reported.

### Required Documentation

Update docs to explain:

- `quantity_item` stores durable quantity results
- quantity generation uses `engineering_class_profiles.json`
- Round 4 does not produce budgets
- `formula` is reserved for later
- `manual_review` rows represent missing data or unsupported methods

After implementation lands:

- mark Milestone 4 as complete
- set Milestone 5 Budgeting as next

### Validation Commands

```powershell
python -m pytest -q
```

## Final Round 4 Acceptance

Round 4 is complete when this works from a clean temporary database:

```powershell
python -m pytest -q
$env:DWG_REC_DB="data/round4_acceptance.db"
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json --strict-taxonomy
python -m dwg_rec_system.cli generate-quantities
python -m dwg_rec_system.cli list-quantities
python -m dwg_rec_system.cli export-quantities-csv
```

Expected:

- tests pass
- `quantity_item` exists
- quantity generation creates rows for profiled sample objects
- rows include unit, quantity, method, group key or evidence
- CSV export succeeds
- no budget rows or budget tables are created

