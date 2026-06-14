# Agent Tasks Round 1

This document defines the first multi-agent implementation round. Each task is intentionally bounded. Agents should not expand scope without reporting back to the coordinator.

## Round Goal

Build the first real ingestion path:

```text
normalized CAD parser JSON
  -> CLI import-json
  -> ObjectInput
  -> ObjectStore
  -> query / inference / export
```

Secondary goal:

```text
taxonomy JSON
  -> object_class table
```

## Coordination Rules

- Every agent must read `CLAUDE.md` and `docs/architecture.md`.
- Every agent must run `python -m pytest -q`.
- Agents must not change `schema.sql` in Round 1.
- Agents must not add third-party dependencies in Round 1.
- Agents must not introduce a web framework, LLM integration, or DWG parser in Round 1.
- Agents must keep edits scoped to their assigned files.
- If two agents need to edit `dwg_rec_system/cli.py`, Agent A should go first and Agent B should rebase or adapt after Agent A.

## Agent A: Normalized JSON Importer

### Objective

Implement a normalized JSON importer and expose it through CLI:

```powershell
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json
```

### Allowed Files

- `dwg_rec_system/importers/`
- `dwg_rec_system/cli.py`
- `tests/`
- `samples/`
- `docs/import_format.md` only if the implementation reveals a necessary correction

### Disallowed Changes

- Do not modify `schema.sql`.
- Do not modify existing dataclass field names in `models.py`.
- Do not bypass `ObjectStore`.
- Do not add external dependencies.
- Do not add a DWG/DXF parser.

### Required Behavior

The importer should:

- Read UTF-8 JSON from `--input`.
- Create or get a project if `project` exists in the JSON.
- Create or get a drawing if `drawing` exists in the JSON.
- Create objects through `ObjectStore.create_object()`.
- Map JSON `geometry` into `GeometryInput`.
- Map JSON `cad_meta` into `CadMetaInput`.
- Map JSON `attributes` into `ObjectInput.attributes`.
- Preserve `source_file` and `handle` so repeated imports update existing objects.
- Resolve `class_id` from `object_class.code` when a matching class exists.
- Return or print a concise import summary: object count, created/updated if practical, drawing ID if present.

### Suggested Design

Create:

```text
dwg_rec_system/importers/__init__.py
dwg_rec_system/importers/normalized_json.py
```

Suggested public API:

```python
class NormalizedJsonImporter:
    def __init__(self, connection): ...
    def import_file(self, path: str | Path) -> dict: ...
    def import_data(self, payload: dict) -> dict: ...
```

### Required Tests

Add tests for:

- importing a sample object with geometry, CAD metadata, and attributes
- repeated import with same `source_file + handle` updates the object
- imported geometry is queryable through `SpatialIndex.nearest` or `contains_point`

### Validation Commands

```powershell
python -m pytest -q
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json
python -m dwg_rec_system.cli list-objects
```

## Agent B: Taxonomy Seeder

### Objective

Implement a taxonomy seeding CLI command:

```powershell
python -m dwg_rec_system.cli seed-taxonomy
```

It should load `dwg_rec_system/taxonomy/cad_object_taxonomy.json` into `object_class`.

### Allowed Files

- `dwg_rec_system/cli.py`
- `dwg_rec_system/services/`
- `dwg_rec_system/repositories.py` only if a small repository helper is needed
- `tests/`
- `README.md` only for the new command line

### Disallowed Changes

- Do not modify the taxonomy JSON structure unless explicitly approved.
- Do not modify `schema.sql`.
- Do not add dependencies.
- Do not hard-code every class in Python.

### Required Behavior

The seeder should:

- Read the taxonomy JSON as UTF-8.
- Insert each `object_classes` entry into `object_class`.
- Use `code` as `object_class.code`.
- Use `name_cn` as `object_class.name`.
- Use `parent_code` as `object_class.parent_code`.
- Use `discipline` as `object_class.discipline`.
- Use a useful text summary as `description`, preferably including aliases and expected attributes.
- Be idempotent: repeated runs must not duplicate classes.

### Suggested Design

Create:

```text
dwg_rec_system/services/taxonomy.py
```

Suggested public API:

```python
class TaxonomySeeder:
    def __init__(self, connection): ...
    def seed_file(self, path: str | Path | None = None) -> dict: ...
```

### Required Tests

Add tests for:

- seeding creates object classes
- repeated seeding does not duplicate object classes
- parent code and discipline are preserved

### Validation Commands

```powershell
python -m pytest -q
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy
```

## Agent C: Test Coverage Consolidation

### Objective

Strengthen tests around import, taxonomy, and existing object flow. Agent C should start after Agents A and B have implementation branches available.

### Allowed Files

- `tests/`
- `samples/`
- test-only helpers if needed

### Disallowed Changes

- Do not change production code except for clearly necessary bug fixes, and report those separately.
- Do not modify schema.
- Do not add dependencies.

### Required Coverage

Add or verify tests for:

- normalized JSON import creates project/drawing/object data
- repeated normalized import updates the same object
- attributes preserve value types enough for current repository behavior
- taxonomy seeding is idempotent
- relation inference still works after imported objects
- CSV export still works after import

### Validation Commands

```powershell
python -m pytest -q
```

## Agent D: Documentation And Sample Data

### Objective

Update documentation so a developer can run the new import flow without reading code.

### Allowed Files

- `README.md`
- `docs/import_format.md`
- `docs/development_plan.md` only for status updates
- `samples/`

### Disallowed Changes

- Do not change production code.
- Do not change tests unless sample data must align with tests.

### Required Output

Add or update:

- `samples/demo_parsed.json`
- README quickstart for `seed-taxonomy` and `import-json`
- import format examples and field descriptions

### Validation Commands

```powershell
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json
python -m dwg_rec_system.cli list-objects
```

If Agent D works before Agent A, it should only add docs/sample data and mark commands as expected after Agent A lands.

## Suggested Round 1 Merge Order

1. Agent A importer
2. Agent B taxonomy seeder
3. Agent C test consolidation
4. Agent D docs/sample cleanup

If branches are independent, Agent B can merge before Agent A. Agent C should run after implementation tasks.

## Final Round 1 Acceptance

Round 1 is complete when this works from the repository root:

```powershell
python -m pytest -q
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json
python -m dwg_rec_system.cli list-objects
python -m dwg_rec_system.cli infer-relations
python -m dwg_rec_system.cli export-csv
```
