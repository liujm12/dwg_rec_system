# Agent Tasks Round 3

Round 3 prepares the engineering knowledge layer needed before quantity takeoff, budgeting, and installation guidance.

Round 2 proved:

```text
seed-taxonomy
  -> import-json --strict-taxonomy
  -> seed-rules
  -> infer-relations
  -> list/review candidates
  -> export-csv
```

Round 3 should make this foundation more useful for the final product goal:

```text
multi-discipline taxonomy profile
  -> expected object attributes
  -> relation hints
  -> budget hints
  -> installation hints
  -> validation tests
```

## Round Goal

Build a multi-discipline taxonomy profile foundation without changing the database schema.

This round should define the engineering dictionary that later quantity, budget, and installation services will consume. It should stay JSON-based for now so the project can learn the right shape before promoting profile fields into durable tables.

## Coordination Rules

- Every agent must read `CLAUDE.md`, `docs/architecture.md`, `docs/final_roadmap.md`, and this file.
- Every agent must run `python -m pytest -q`.
- Do not modify `schema.sql` in Round 3.
- Do not add third-party dependencies in Round 3.
- Do not implement quantity, budget, installation, API, LLM, DWG, or DXF runtime logic in Round 3.
- Keep importers writing through `ObjectStore`.
- Keep relation inference flowing through `relation_candidate -> relation`.
- Prefer taxonomy/profile configuration over hard-coded discipline behavior.

## Proposed Profile Shape

Use JSON entries with this general shape:

```json
{
  "code": "VALVE",
  "name_cn": "Valve",
  "discipline": "PLUMBING",
  "parent_code": "PIPE_ACCESSORY",
  "aliases": ["valve", "control valve"],
  "expected_attributes": [
    "tag",
    "diameter",
    "material",
    "pressure_rating",
    "system"
  ],
  "relations": [
    "installed_on",
    "connected_to",
    "located_in",
    "belongs_to_system"
  ],
  "budget": {
    "unit": "pcs",
    "quantity_method": "count_by_object",
    "group_by": ["diameter", "material", "pressure_rating"]
  },
  "installation": {
    "work_package": "pipe accessory installation",
    "default_steps": [
      "verify type and specification",
      "confirm installation location and flow direction",
      "install and connect",
      "inspect sealing",
      "label and record"
    ],
    "required_predecessors": ["PIPE_INSTALLED"]
  }
}
```

Allowed profile fields:

- `code`
- `name_cn`
- `discipline`
- `parent_code`
- `aliases`
- `expected_attributes`
- `relations`
- `budget`
- `installation`
- `description`

## Agent A: Multi-Discipline Taxonomy Profile

### Objective

Create a multi-discipline taxonomy profile JSON file.

Recommended file:

```text
dwg_rec_system/taxonomy/multi_discipline_taxonomy.json
```

### Allowed Files

- `dwg_rec_system/taxonomy/`
- `tests/`
- `docs/`

### Disallowed Changes

- Do not modify `schema.sql`.
- Do not modify production Python unless a small loader helper is explicitly needed.
- Do not replace `cleanroom_cad_taxonomy.json`.
- Do not remove existing taxonomy entries.
- Do not add external dependencies.

### Required Scope

Cover these initial disciplines:

- `HVAC`
- `PLUMBING`
- `ELEC`
- `BAS_ICA`
- `CLEANROOM`

Suggested first target:

- at least 10 classes per discipline
- each class has `code`, `name_cn`, `discipline`, and `expected_attributes`
- each class has either a `budget` profile or a clear reason in `description`
- each class has installation hints when installation is meaningful

### Required Tests

Add tests that verify:

- JSON is valid UTF-8.
- Top-level `object_classes` exists and is a list.
- Class codes are unique.
- Required disciplines are present.
- Required fields exist on every class.
- `budget.quantity_method`, when present, is one of the approved methods.
- `installation.default_steps`, when present, is a list.

### Validation Commands

```powershell
python -m pytest -q
```

## Agent B: Taxonomy Profile Documentation

### Objective

Document how the multi-discipline profile should be used by future quantity, budget, and installation services.

### Allowed Files

- `docs/`
- `README.md`

### Disallowed Changes

- Do not modify production Python.
- Do not modify database schema.
- Do not add new runtime behavior.

### Required Documentation

Add or update documentation for:

- taxonomy profile shape
- approved disciplines
- approved quantity methods
- relationship between taxonomy profile and `object_class`
- why Round 3 avoids schema changes
- how future quantity/budget/installation services should consume the profile

Suggested file:

```text
docs/taxonomy_profile.md
```

### Validation Commands

```powershell
python -m pytest -q
```

## Agent C: Seeder Compatibility Review

### Objective

Verify whether the current `TaxonomySeeder` can seed the new multi-discipline profile without schema changes.

### Allowed Files

- `dwg_rec_system/services/taxonomy.py`
- `tests/`
- `docs/`

### Disallowed Changes

- Do not modify `schema.sql`.
- Do not add profile-specific columns.
- Do not hard-code all profile fields into Python conditionals.

### Required Behavior

If the current seeder can already seed the new profile safely:

- add tests that prove it
- document the limitation that richer profile fields are currently summarized into `description`

If a small compatibility change is needed:

- keep it focused
- preserve idempotency
- keep `object_class.code`, `name`, `parent_code`, and `discipline` mapping unchanged
- summarize aliases, expected attributes, budget hints, installation hints, and relations into `description`

### Required Tests

Add tests for:

- seeding multi-discipline profile creates classes
- repeated seeding is idempotent
- discipline and parent code are preserved
- description contains enough profile hints for later review

### Validation Commands

```powershell
python -m pytest -q
```

## Agent D: Round 3 Acceptance And Plan Update

### Objective

Update the project plan after Round 3 implementation lands.

### Allowed Files

- `docs/development_plan.md`
- `docs/final_roadmap.md`
- `README.md`

### Disallowed Changes

- Do not modify production code.
- Do not modify tests unless documentation examples require sample alignment.

### Required Updates

After Round 3 is implemented and tested:

- mark Milestone 3 as complete
- set Milestone 4 Quantity Takeoff as next
- keep warnings that quantity and budget tables require explicit schema tasks
- document the multi-discipline taxonomy profile as the engineering dictionary source

## Approved Quantity Methods

Use these method names for Round 3 profile validation:

```text
count_by_object
length_by_geometry
area_by_geometry
grouped_count
formula
manual_review
```

## Final Round 3 Acceptance

Round 3 is complete when:

```powershell
python -m pytest -q
```

passes and the repository contains:

- a multi-discipline taxonomy profile
- validation tests for the profile
- documentation explaining the profile
- seeder compatibility tests or a clear documented limitation

Expected:

- at least 5 disciplines are represented
- class codes are unique
- profile shape is stable enough for Round 4 quantity takeoff design
- no database schema changes are made

