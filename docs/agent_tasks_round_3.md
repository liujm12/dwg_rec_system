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

Round 3 adds an engineering profile overlay on top of the primary CAD object taxonomy:

```text
cad_object_taxonomy.json
  -> object_class

engineering_class_profiles.json
  -> expected attributes
  -> relation hints
  -> budget hints
  -> installation hints
  -> validation tests
```

## Round Goal

Build a multi-discipline engineering class profile foundation without changing the database schema.

The project has one primary object taxonomy:

```text
dwg_rec_system/taxonomy/cad_object_taxonomy.json
```

Round 3 must not create a second competing taxonomy. It should add a profile overlay:

```text
dwg_rec_system/taxonomy/engineering_class_profiles.json
```

Each profile entry must reference an existing `code` from `cad_object_taxonomy.json`.

## Coordination Rules

- Every agent must read `CLAUDE.md`, `docs/architecture.md`, `docs/final_roadmap.md`, and this file.
- Every agent must run `python -m pytest -q`.
- Do not modify `schema.sql` in Round 3.
- Do not add third-party dependencies in Round 3.
- Do not implement quantity, budget, installation, API, LLM, DWG, or DXF runtime logic in Round 3.
- Do not create a second object class taxonomy.
- Keep `cad_object_taxonomy.json` as the only source for `object_class`.
- Keep `engineering_class_profiles.json` as a profile overlay only.
- Prefer taxonomy/profile configuration over hard-coded discipline behavior.

## Proposed Profile Shape

Use JSON entries with this shape:

```json
{
  "code": "VALVE",
  "profile_group": "PIPING",
  "expected_attributes": [
    "tag",
    "diameter",
    "valve_type",
    "material",
    "pressure_rating",
    "medium"
  ],
  "relations": [
    "installed_on",
    "connected_to",
    "located_in"
  ],
  "budget": {
    "unit": "pcs",
    "quantity_method": "count_by_object",
    "group_by": ["diameter", "valve_type", "material"]
  },
  "installation": {
    "work_package": "pipe accessory installation",
    "default_steps": [
      "verify valve spec",
      "confirm flow direction",
      "install valve",
      "inspect sealing",
      "tag valve"
    ],
    "required_predecessors": ["PIPE_SECTION_READY"]
  }
}
```

Allowed profile fields:

- `code`
- `profile_group`
- `expected_attributes`
- `relations`
- `budget`
- `installation`
- `description`

Fields such as `name_cn`, `discipline`, `parent_code`, and `aliases` belong to `cad_object_taxonomy.json`, not the profile overlay.

## Agent A: Engineering Class Profile Overlay

### Objective

Create the engineering profile overlay.

Required file:

```text
dwg_rec_system/taxonomy/engineering_class_profiles.json
```

### Allowed Files

- `dwg_rec_system/taxonomy/`
- `tests/`
- `docs/`

### Disallowed Changes

- Do not modify `schema.sql`.
- Do not replace `cad_object_taxonomy.json`.
- Do not add profile entries for unknown object class codes.
- Do not add external dependencies.

### Required Scope

Cover these initial profile groups:

- `HVAC`
- `PIPING`
- `ELEC`
- `BMS`
- `CLEANROOM`

Suggested first target:

- at least 5 representative profiles per profile group
- every profile `code` exists in `cad_object_taxonomy.json`
- every profile has `expected_attributes`
- every profile has either a `budget` profile or a clear reason in `description`
- every profile has installation hints when installation is meaningful

### Required Tests

Add tests that verify:

- `cad_object_taxonomy.json` is the base taxonomy.
- `engineering_class_profiles.json` is valid UTF-8 JSON.
- Top-level `class_profiles` exists and is a list.
- Profile codes are unique.
- Every profile code exists in `cad_object_taxonomy.json`.
- Required profile groups are present.
- Required fields exist on every profile.
- `budget.quantity_method`, when present, is one of the approved methods.
- `installation.default_steps`, when present, is a list.

### Validation Commands

```powershell
python -m pytest -q
```

## Agent B: Taxonomy Profile Documentation

### Objective

Document how the engineering profile overlay should be used by future quantity, budget, and installation services.

### Allowed Files

- `docs/`
- `README.md`

### Disallowed Changes

- Do not modify production Python.
- Do not modify database schema.
- Do not add new runtime behavior.

### Required Documentation

Add or update documentation for:

- base taxonomy vs engineering profile overlay
- profile shape
- approved profile groups
- approved quantity methods
- why Round 3 avoids schema changes
- why profile entries must reference existing object class codes
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

Verify that `TaxonomySeeder` still seeds only the primary taxonomy into `object_class`.

### Allowed Files

- `dwg_rec_system/services/taxonomy.py`
- `tests/`
- `docs/`

### Disallowed Changes

- Do not modify `schema.sql`.
- Do not add profile-specific columns.
- Do not seed `engineering_class_profiles.json` into `object_class`.
- Do not hard-code all profile fields into Python conditionals.

### Required Behavior

The default `TaxonomySeeder.seed_file()` should load:

```text
dwg_rec_system/taxonomy/cad_object_taxonomy.json
```

The engineering profile overlay should remain a separate JSON input for later services. It is validated by tests but not seeded into `object_class`.

### Required Tests

Add tests for:

- default seeding uses the primary taxonomy
- engineering profile codes all exist in the primary taxonomy
- profile validation does not require database schema changes

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
- document `cad_object_taxonomy.json` as the primary object taxonomy
- document `engineering_class_profiles.json` as the engineering profile overlay

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

- a renamed primary taxonomy: `cad_object_taxonomy.json`
- an engineering profile overlay: `engineering_class_profiles.json`
- validation tests for the overlay
- documentation explaining base taxonomy vs overlay

Expected:

- at least 5 profile groups are represented
- profile codes are unique
- every profile code exists in the primary taxonomy
- profile shape is stable enough for Round 4 quantity takeoff design
- no database schema changes are made
