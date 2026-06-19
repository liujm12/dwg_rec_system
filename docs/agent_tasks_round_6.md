# Agent Tasks Round 6

Round 6 turns reviewed quantity rows into auditable budget rows.

Round 4 provided:

```text
cad_object + geometry + attribute + engineering_class_profiles.json
  -> quantity_item
```

Round 5 provided:

```text
cad_object + attribute + geometry + relation + quantity_item
  -> data quality findings
```

Round 6 should make this work:

```text
seed-taxonomy
  -> import-json --strict-taxonomy
  -> generate-quantities
  -> check-data-quality
  -> seed-cost-items
  -> generate-budget
  -> list-budget-items
  -> export-budget-csv
```

## Round Goal

Implement the first budgeting workflow on top of `quantity_item`.

The output of Round 6 is not an installation plan, workflow schedule, real market pricing integration, API, UI, parser, or LLM feature. It is an auditable budget layer that records how a quantity item was matched to a cost item and how the first budget totals were calculated.

Round 6 should answer questions like:

```text
Which quantity items can be priced?
Which cost item matched each quantity item?
How much material, labor, machine, and total cost does each budget item carry?
Which quantity items need review because no cost item matched?
Can budget rows be exported for review?
```

## Coordination Rules

- Every agent must read `CLAUDE.md`, `docs/architecture.md`, `docs/final_roadmap.md`, `docs/taxonomy_profile.md`, `docs/agent_tasks_round_4.md`, `docs/agent_tasks_round_5.md`, and this file.
- Every agent must run `python -m pytest -q`.
- Do not implement installation tables or installation services in Round 6.
- Do not implement workflow planning in Round 6.
- Do not implement DWG/DXF/PDF parsing, API, UI, or LLM behavior.
- Do not add external dependencies.
- Keep object import through `ObjectStore`.
- Keep quantity generation through `QuantityGenerator`.
- Keep data quality checks available before budgeting, but do not make budget generation depend on a durable findings table.
- Keep budget matching deterministic and explainable.
- Do not overwrite or mutate `quantity_item` rows when generating budgets.

## Schema Boundary

Round 6 is an explicit architecture task for budget tables.

Allowed schema additions:

```text
cost_item
budget_item
```

Do not modify existing core table semantics:

- `cad_object`
- `geometry`
- `cad_meta`
- `attribute`
- `relation_candidate`
- `relation`
- `quantity_item`

Do not add installation tables in Round 6.

## Cost Item Contract

`cost_item` is the price or quota library. It should be seedable from JSON and reusable across projects.

Suggested fields:

```text
id
code
name
discipline
class_code
spec_pattern
unit
unit_price_material
unit_price_labor
unit_price_machine
currency
region
version
effective_from
effective_to
description
status
created_at
updated_at
```

Recommended constraints:

- `code` should be unique.
- `unit_price_material`, `unit_price_labor`, and `unit_price_machine` should default to `0`.
- Prices should be non-negative.
- `status` should support at least:

```text
active
inactive
```

Round 6 does not need a full quota library. A small deterministic sample cost item file is enough.

## Budget Item Contract

`budget_item` stores project-specific budget results generated from `quantity_item`.

Suggested fields:

```text
id
project_id
drawing_id
quantity_item_id
cost_item_id
discipline
item_name
spec
unit
quantity
unit_price_material
unit_price_labor
unit_price_machine
material_cost
labor_cost
machine_cost
total_cost
pricing_source
confidence
evidence_json
status
created_at
updated_at
```

Suggested `status` values:

```text
auto
review
matched
unmatched
corrected
rejected
```

Recommended semantics:

- Matched budget rows should reference both `quantity_item_id` and `cost_item_id`.
- Unmatched quantity rows may produce a `budget_item` with `cost_item_id = NULL`, zero cost, and `status = 'unmatched'`, or they may be reported in the summary only. Prefer creating unmatched budget rows so reviewers can export and inspect them.
- Budget rows should preserve quantity values from `quantity_item`; do not recalculate engineering quantities in the budget service.
- Budget evidence should explain match method, score, candidate cost item code, and source quantity item id.

## Budget Matching Semantics

Round 6 matching should be deterministic and conservative.

Initial matching order:

1. Exact `class_code` and exact `unit`.
2. If multiple active cost items match, prefer the one whose `spec_pattern` is empty or appears in `quantity_item.spec`.
3. If still tied, pick the lowest sorted `cost_item.code` for deterministic behavior.
4. If no active cost item matches, create an unmatched budget row or include the quantity item in an unmatched list.

Round 6 should not use fuzzy matching, embeddings, LLM matching, web pricing, or regional market data.

Suggested match evidence:

```json
{
  "quantity_item_id": "...",
  "cost_item_id": "...",
  "cost_item_code": "BMS-CP-001",
  "match_method": "class_code_unit",
  "match_score": 1.0,
  "matched_fields": ["class_code", "unit"],
  "spec_pattern": "optional"
}
```

## Cost Calculation Semantics

For each matched row:

```text
material_cost = quantity * unit_price_material
labor_cost = quantity * unit_price_labor
machine_cost = quantity * unit_price_machine
total_cost = material_cost + labor_cost + machine_cost
```

Use floating point values consistently with the current SQLite prototype. Round 6 does not need tax, overhead, profit, discount, region coefficient, or currency conversion.

Confidence suggestion:

- matched row: use `quantity_item.confidence`
- unmatched row: use `min(quantity_item.confidence, 0.5)`

## Data Quality Boundary

Round 6 should integrate with Round 5 cautiously:

- `generate-budget` may run even when data quality findings exist.
- Budget evidence should preserve quantity evidence and cost match evidence.
- If a `quantity_item` uses `manual_review`, generated budget status should be `review` or `unmatched` unless an explicit cost match exists and the implementation clearly marks it as review-needed.
- Do not block budget generation solely because `check-data-quality` reports findings.
- Do not create a durable data quality findings table in Round 6.

## Agent A: Budget Schema And Repositories

### Objective

Add schema and repository support for budget cost libraries and generated budget rows.

### Allowed Files

- `dwg_rec_system/schema.sql`
- `dwg_rec_system/db.py`
- `dwg_rec_system/repositories.py`
- `tests/`
- `docs/` only for clarifying behavior

### Disallowed Changes

- Do not modify existing core table semantics.
- Do not add installation tables.
- Do not add parser, API, UI, or LLM behavior.
- Do not add external dependencies.

### Required Behavior

Add schema for:

```text
cost_item
budget_item
```

Update SQLite compatibility setup in `dwg_rec_system/db.py` for existing local databases.

Add repositories such as:

```python
class CostItemRepository:
    def upsert(...): ...
    def list(...): ...
    def find_matches(...): ...

class BudgetItemRepository:
    def create(...): ...
    def clear_auto(...): ...
    def list(...): ...
```

Suggested behavior:

- `CostItemRepository.upsert` should be idempotent by `code`.
- `CostItemRepository.list` should support filters:
  - `class_code`
  - `discipline`
  - `unit`
  - `status`
- `CostItemRepository.find_matches` should return deterministic active candidates for `class_code` and `unit`.
- `BudgetItemRepository.clear_auto` may delete generated rows before regeneration but must not delete `corrected` or `rejected` rows.
- `BudgetItemRepository.list` should support filters:
  - `project_id`
  - `drawing_id`
  - `class_code` if stored or inferable
  - `status`

### Required Tests

Add tests for:

- `cost_item` and `budget_item` tables exist with expected columns
- cost item upsert is idempotent by code
- active cost item matching by `class_code` and `unit`
- budget item creation
- budget regeneration preserves non-auto/corrected rows

### Validation Commands

```powershell
python -m pytest -q
```

## Agent B: Cost Item Seeder

### Objective

Seed a deterministic sample cost library from JSON.

### Allowed Files

- `dwg_rec_system/services/`
- `dwg_rec_system/repositories.py`
- `samples/`
- `tests/`
- `README.md`
- `docs/`

### Disallowed Changes

- Do not implement external price lookup.
- Do not add dependencies.
- Do not seed engineering profiles into cost items automatically.

### Required Files

Create a sample file such as:

```text
samples/demo_cost_items.json
```

Suggested shape:

```json
{
  "version": "0.1",
  "cost_items": [
    {
      "code": "BMS-CONTROL-PANEL-SET",
      "name": "Control panel",
      "discipline": "BMS",
      "class_code": "CONTROL_PANEL",
      "spec_pattern": "",
      "unit": "set",
      "unit_price_material": 1000,
      "unit_price_labor": 300,
      "unit_price_machine": 50,
      "currency": "CNY",
      "region": "DEFAULT",
      "version": "2026.1"
    }
  ]
}
```

Create a service such as:

```python
class CostItemSeeder:
    def seed_file(path: str | Path) -> dict: ...
```

### Required Tests

Add tests for:

- seed sample cost items
- repeat seeding does not duplicate rows
- invalid or missing required fields produce clear errors

### Validation Commands

```powershell
python -m pytest -q
```

## Agent C: Budget Service

### Objective

Generate `budget_item` rows from `quantity_item` rows and seeded `cost_item` rows.

### Allowed Files

- `dwg_rec_system/services/`
- `dwg_rec_system/repositories.py`
- `tests/`
- `docs/` only for clarifying behavior

### Disallowed Changes

- Do not recalculate quantities.
- Do not modify `quantity_item`.
- Do not use LLM, web pricing, or fuzzy matching.
- Do not implement installation behavior.
- Do not add external dependencies.

### Required Behavior

Create:

```text
dwg_rec_system/services/budget.py
```

Suggested API:

```python
class BudgetGenerator:
    def __init__(self, connection): ...
    def generate(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> dict: ...
```

The generator should:

- clear old generated budget rows for the selected scope
- read `quantity_item` rows
- find matching active `cost_item` rows
- create matched `budget_item` rows with calculated costs
- create unmatched/review rows when no cost item matches
- include evidence JSON with quantity and match context
- return summary:

```json
{
  "quantities_total": 0,
  "created": 0,
  "matched": 0,
  "unmatched": 0,
  "review": 0,
  "cleared": 0,
  "total_cost": 0
}
```

### Required Tests

Add tests for:

- matched quantity creates budget row
- cost calculation is correct
- unmatched quantity creates reviewable/unmatched row
- manual review quantity does not silently become fully matched without review status
- repeated generation is idempotent for auto rows
- project/drawing filters
- evidence includes quantity item and cost item context

### Validation Commands

```powershell
python -m pytest -q
```

## Agent D: Budget CLI And Export

### Objective

Expose cost item seeding, budget generation, budget listing, and budget CSV export.

### Required Commands

```powershell
python -m dwg_rec_system.cli seed-cost-items --input samples/demo_cost_items.json
python -m dwg_rec_system.cli list-cost-items
python -m dwg_rec_system.cli generate-budget
python -m dwg_rec_system.cli list-budget-items
python -m dwg_rec_system.cli export-budget-csv
```

Optional filters:

```powershell
list-cost-items --class-code CONTROL_PANEL --status active
generate-budget --project-id <id> --drawing-id <id>
list-budget-items --status unmatched
export-budget-csv --output exports/budget.csv
```

### Allowed Files

- `dwg_rec_system/cli.py`
- `dwg_rec_system/services/`
- `dwg_rec_system/repositories.py`
- `tests/`
- `README.md`
- `docs/`

### Disallowed Changes

- Do not implement Excel export in Round 6 unless already trivial from existing code.
- Do not implement budget API.
- Do not modify object import behavior.
- Do not add external dependencies.

### Required Behavior

`seed-cost-items` should:

- load cost items from JSON
- upsert by cost item `code`
- print JSON summary

`list-cost-items` should:

- print cost rows as JSON
- support class/status/unit filters

`generate-budget` should:

- run `BudgetGenerator`
- print JSON summary

`list-budget-items` should:

- print budget rows as JSON
- support project/drawing/status filters

`export-budget-csv` should:

- write budget rows to CSV
- default to `exports/budget.csv`
- include enough fields for review:
  - quantity_item_id
  - cost_item_id
  - discipline
  - item_name
  - spec
  - unit
  - quantity
  - unit prices
  - material/labor/machine/total costs
  - pricing_source
  - status
  - confidence

### Required Tests

Add tests for:

- CLI commands print valid JSON where expected
- sample cost item seeding works
- full command flow works after sample import, quantity generation, and quality check
- CSV export writes expected headers
- filters work

### Validation Commands

```powershell
python -m pytest -q
```

## Agent E: Documentation And Acceptance

### Objective

Document the budgeting workflow and update the development plan after implementation lands.

### Allowed Files

- `README.md`
- `docs/development_plan.md`
- `docs/final_roadmap.md`
- `docs/agent_tasks_round_6.md`
- `samples/` only for sample cost item data

### Disallowed Changes

- Do not modify production code.
- Do not add installation, parser, API, UI, or LLM behavior.

### Required Documentation

Update docs to explain:

- `quantity_item` answers "how much"
- `cost_item` answers "what price rule"
- `budget_item` answers "project-specific cost result"
- Round 6 uses deterministic matching, not fuzzy matching or LLM pricing
- unmatched rows are reviewable output, not silent failures
- budget generation does not mutate `quantity_item`
- budget generation may run when data quality findings exist, but findings should be reviewed before budget results are trusted

After implementation lands:

- mark Milestone 6 as complete
- set Milestone 7 Installation Guidance as next

### Validation Commands

```powershell
python -m pytest -q
```

## Final Round 6 Acceptance

Round 6 is complete when this works from a clean temporary database:

```powershell
python -m pytest -q
$env:DWG_REC_DB="data/round6_acceptance.db"
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json --strict-taxonomy
python -m dwg_rec_system.cli generate-quantities
python -m dwg_rec_system.cli check-data-quality
python -m dwg_rec_system.cli seed-cost-items --input samples/demo_cost_items.json
python -m dwg_rec_system.cli generate-budget
python -m dwg_rec_system.cli list-budget-items
python -m dwg_rec_system.cli export-budget-csv
```

Expected:

- tests pass
- `cost_item` and `budget_item` exist
- sample cost items seed idempotently
- generated quantities can produce budget rows
- matched rows contain calculated material, labor, machine, and total costs
- unmatched rows are visible for review
- budget rows preserve references to source `quantity_item` and matched `cost_item`
- CSV export succeeds
- no installation rows or installation tables are created
- no parser adapters, API, UI, LLM behavior, web pricing, fuzzy matching, or external dependencies are added

