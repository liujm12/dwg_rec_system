# Agent Tasks Round 5

Round 5 adds a data quality gate between quantity takeoff and budgeting.

Round 4 provided:

```text
cad_object + geometry + attribute + engineering_class_profiles.json
  -> quantity_item
```

Round 5 should make this work:

```text
seed-taxonomy
  -> import-json --strict-taxonomy
  -> generate-quantities
  -> check-data-quality
  -> list-quality-findings
  -> export-quality-findings-csv
```

## Round Goal

Implement the first reviewable data quality workflow.

The output of Round 5 is not a budget, installation plan, recognition model, or parser. It is a deterministic findings layer that tells later budget and installation services where the input data is weak.

Round 5 should answer questions like:

```text
Which objects are missing expected attributes?
Which objects do not have geometry needed for quantity generation?
Which recognized objects have low confidence?
Which generated quantities need manual review?
Which object classes lack accepted relations that are important for budgeting or installation?
```

## Coordination Rules

- Every agent must read `CLAUDE.md`, `docs/architecture.md`, `docs/final_roadmap.md`, `docs/taxonomy_profile.md`, `docs/agent_tasks_round_4.md`, and this file.
- Every agent must run `python -m pytest -q`.
- Do not add budget tables or budget services in Round 5.
- Do not add installation tables or installation services in Round 5.
- Do not implement DWG/DXF/PDF parsing, API, UI, or LLM behavior.
- Do not add external dependencies.
- Keep engineering profiles as configuration, not hard-coded class behavior.
- Keep object import through `ObjectStore`.
- Do not modify `schema.sql` unless a schema bug is found and reported first.
- Round 5 should default to non-durable findings returned by service methods and CLI JSON/CSV output. A durable findings table can be considered in a later architecture task after the finding shape stabilizes.

## Data Quality Finding Contract

Round 5 should use a structured finding shape consistently in service results, CLI JSON, and CSV export.

Suggested finding fields:

```text
finding_id
severity
category
code
message
project_id
drawing_id
object_id
quantity_item_id
class_code
discipline
profile_group
field_name
expected
actual
source
evidence
status
```

Allowed severities:

```text
error
warning
info
```

Initial categories:

```text
missing_attribute
missing_geometry
low_confidence
manual_review_quantity
missing_relation
missing_profile
```

Initial status:

```text
open
```

`evidence` should be JSON-serializable and include enough context for review, such as profile code, required attribute, quantity method, confidence threshold, relation type, source object id, or quantity item id.

## Data Quality Semantics

### Missing Expected Attribute

Use `engineering_class_profiles.json`.

For each object with a matching profile:

- read `expected_attributes`
- read object `attribute` rows
- create one finding for each missing or empty expected attribute

Suggested severity:

```text
warning
```

If the missing attribute is also used by `budget.group_by`, severity may be:

```text
error
```

### Missing Geometry

Use profile `budget.quantity_method`.

Create findings when a method needs geometry and the object lacks enough geometry data:

- `length_by_geometry` needs one of:
  - `raw_geometry.length`
  - `geometry.width`
  - `geometry.height`
- `area_by_geometry` needs one of:
  - `raw_geometry.area`
  - both `geometry.width` and `geometry.height`

Suggested severity:

```text
error
```

### Low Confidence Object

Create a finding when `cad_object.confidence` is below a configurable threshold.

Default threshold:

```text
0.80
```

Suggested severity:

```text
warning
```

### Manual Review Quantity

Create a finding for each `quantity_item` where:

```text
quantity_method = 'manual_review'
```

Suggested severity:

```text
error
```

Evidence should include `quantity_item.evidence_json` when present.

### Missing Engineering Profile

Create a finding for objects whose `cad_object.class` is not present in `engineering_class_profiles.json`.

Suggested severity:

```text
info
```

Reason:

Some objects, such as text labels or dimensions, may not need quantity, budget, or installation behavior. This should still be visible before budgeting.

### Missing Accepted Relation

Use profile `relations`.

Round 5 should check only for relation types declared in a configurable required relation list. Do not treat every profile relation hint as mandatory by default.

Suggested default required relation types:

```text
located_in
belongs_to_system
connected_to
mounted_on
powered_by
controlled_by
```

Create a finding when:

- the object's profile lists the relation type
- the relation type is in the required relation list
- no active accepted `relation` exists where the object is either source or target for that relation type

Suggested severity:

```text
warning
```

Round 5 should not infer missing relations. It should only report that accepted relation evidence is missing.

## Agent A: Data Quality Service

### Objective

Create a service that produces data quality findings from objects, attributes, geometry, relations, quantities, and engineering profiles.

### Allowed Files

- `dwg_rec_system/services/`
- `tests/`
- `docs/` only for clarifying behavior

### Disallowed Changes

- Do not modify `schema.sql` unless a schema bug is found and reported.
- Do not add repository writes for findings in Round 5.
- Do not implement budget, installation, parser, API, UI, or LLM behavior.
- Do not hard-code class-specific rules when engineering profiles can provide the needed behavior.
- Do not add external dependencies.

### Required Behavior

Create:

```text
dwg_rec_system/services/data_quality.py
```

Suggested API:

```python
class DataQualityChecker:
    def __init__(
        self,
        connection,
        profile_path: str | Path | None = None,
        low_confidence_threshold: float = 0.8,
        required_relation_types: list[str] | None = None,
    ): ...

    def check(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> dict: ...
```

Suggested return shape:

```json
{
  "summary": {
    "objects_checked": 0,
    "quantities_checked": 0,
    "findings_total": 0,
    "by_severity": {"error": 0, "warning": 0, "info": 0},
    "by_category": {}
  },
  "findings": []
}
```

The checker should:

- load `engineering_class_profiles.json`
- query objects, geometry, attributes, accepted relations, and quantity rows
- produce findings for the categories defined above
- include object and quantity references when available
- keep findings deterministic and sorted for stable tests

### Required Tests

Add tests for:

- missing expected attributes
- missing `budget.group_by` attributes have higher severity than ordinary expected attributes
- missing length geometry
- missing area geometry
- low confidence objects
- manual review quantities
- objects without engineering profiles
- missing accepted relations
- project/drawing filters

### Validation Commands

```powershell
python -m pytest -q
```

## Agent B: Data Quality CLI

### Objective

Expose data quality checking through CLI commands.

### Required Commands

```powershell
python -m dwg_rec_system.cli check-data-quality
python -m dwg_rec_system.cli list-quality-findings
python -m dwg_rec_system.cli export-quality-findings-csv
```

Optional filters:

```powershell
check-data-quality --project-id <id> --drawing-id <id>
check-data-quality --low-confidence-threshold 0.75
list-quality-findings --severity error --category missing_geometry
export-quality-findings-csv --output exports/quality_findings.csv
```

### Allowed Files

- `dwg_rec_system/cli.py`
- `dwg_rec_system/services/`
- `tests/`
- `README.md`
- `docs/`

### Disallowed Changes

- Do not modify `schema.sql` unless a schema bug is found and reported.
- Do not create a durable findings table in Round 5.
- Do not implement budget export here.
- Do not modify object import behavior.

### Required Behavior

`check-data-quality` should:

- run `DataQualityChecker`
- print JSON summary and findings

`list-quality-findings` should:

- run `DataQualityChecker`
- print findings as JSON
- support filters:
  - `severity`
  - `category`
  - `project_id`
  - `drawing_id`

Because findings are not durable in Round 5, `list-quality-findings` recomputes findings rather than reading a findings table.

`export-quality-findings-csv` should:

- run `DataQualityChecker`
- write findings to CSV
- default to `exports/quality_findings.csv`
- include enough fields for review:
  - severity
  - category
  - code
  - message
  - project_id
  - drawing_id
  - object_id
  - quantity_item_id
  - class_code
  - field_name
  - expected
  - actual
  - status

### Required Tests

Add tests for:

- CLI commands print valid JSON where expected
- severity/category filters work
- CSV export writes expected headers
- command flow works after sample import and quantity generation

### Validation Commands

```powershell
python -m pytest -q
```

## Agent C: Data Quality Export

### Objective

Add CSV export support for data quality findings.

### Allowed Files

- `dwg_rec_system/services/exports.py`
- `dwg_rec_system/services/data_quality.py`
- `tests/`

### Disallowed Changes

- Do not change object CSV export behavior.
- Do not change quantity CSV export behavior except where needed to avoid duplication.
- Do not add external dependencies.

### Required Behavior

Add export behavior such as:

```python
CsvExporter.export_quality_findings(path, findings)
```

The exporter should:

- create parent directories
- write UTF-8 BOM CSV, consistent with existing exports
- write a stable header even when findings are empty
- serialize nested `expected`, `actual`, and `evidence` values as JSON strings when needed

### Required Tests

Add tests for:

- empty findings still produce a header
- nested evidence is serialized safely
- exported CSV can be read by `csv.DictReader`

### Validation Commands

```powershell
python -m pytest -q
```

## Agent D: Documentation And Acceptance

### Objective

Document the data quality workflow and update the development plan after implementation lands.

### Allowed Files

- `README.md`
- `docs/development_plan.md`
- `docs/final_roadmap.md`
- `docs/agent_tasks_round_5.md`
- `samples/` only if a sample import file needs quality-check examples

### Disallowed Changes

- Do not modify production code.
- Do not modify schema unless a bug is found and reported.

### Required Documentation

Update docs to explain:

- Round 5 produces findings, not budgets
- findings are recomputed by default and not durable in Round 5
- engineering profiles drive expected attributes, quantity geometry checks, and relation hints
- `manual_review` quantity rows are treated as quality findings
- low confidence thresholds are configurable
- budget generation should wait until findings are reviewed or accepted as known risk

After implementation lands:

- mark Milestone 5 as complete
- set Milestone 6 Budgeting as next

### Validation Commands

```powershell
python -m pytest -q
```

## Final Round 5 Acceptance

Round 5 is complete when this works from a clean temporary database:

```powershell
python -m pytest -q
$env:DWG_REC_DB="data/round5_acceptance.db"
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json --strict-taxonomy
python -m dwg_rec_system.cli generate-quantities
python -m dwg_rec_system.cli check-data-quality
python -m dwg_rec_system.cli list-quality-findings
python -m dwg_rec_system.cli export-quality-findings-csv
```

Expected:

- tests pass
- data quality commands print valid JSON where expected
- findings include missing expected attributes for the current demo sample
- findings can include missing accepted relations when profile relation hints require them
- CSV export succeeds
- no budget rows, budget tables, installation rows, installation tables, parser adapters, API, UI, or LLM behavior are added

