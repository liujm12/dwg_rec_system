# Agent Tasks Round 2

Round 2 turns the normalized import foundation into a more useful engineering inference workflow.

Round 1 proved:

```text
seed-taxonomy -> import-json -> list-objects -> export-csv
```

Round 2 should make this work:

```text
seed-taxonomy
  -> import-json
  -> seed-rules
  -> infer-relations
  -> list/review relation candidates
  -> export-csv
```

## Round Goal

Build a deterministic, reviewable rule workflow around imported objects:

- Rules can be seeded from JSON.
- Imported objects can infer relations using those rules.
- Candidate relations can be listed, accepted, and rejected through CLI.
- `import-json` can run in strict taxonomy mode for production-like validation.
- The README shows a complete end-to-end demo that actually produces a relation.

## Coordination Rules

- Every agent must read `CLAUDE.md`, `docs/architecture.md`, and this file.
- Every agent must run `python -m pytest -q`.
- Do not modify `schema.sql` in Round 2.
- Do not add third-party dependencies in Round 2.
- Do not implement a DWG/DXF parser in Round 2.
- Do not introduce a web framework or LLM integration in Round 2.
- Preserve the `relation_candidate -> relation` boundary.
- Keep all new behavior reachable from CLI and tests.
- If multiple agents need `dwg_rec_system/cli.py`, merge in this order: Agent A, Agent B, Agent C, Agent D.

## Agent A: Rule Template Importer

### Objective

Implement JSON-driven rule seeding:

```powershell
python -m dwg_rec_system.cli seed-rules --input samples/demo_rules.json
```

This should allow the import sample to produce a `mounted_on` relation after running `infer-relations`.

### Allowed Files

- `dwg_rec_system/cli.py`
- `dwg_rec_system/services/`
- `dwg_rec_system/repositories.py` only if a small helper is needed
- `samples/`
- `tests/`
- `docs/` only if documenting the rule format

### Disallowed Changes

- Do not modify `schema.sql`.
- Do not change `RuleTemplateInput` field names unless explicitly approved.
- Do not change `RelationEngine` semantics except for a clearly required bug fix.
- Do not auto-accept arbitrary LLM/parser suggestions.
- Do not add dependencies.

### Required Rule Format

Create `samples/demo_rules.json`:

```json
{
  "version": "0.1",
  "rules": [
    {
      "name": "DDC mounted on nearest control panel",
      "source_class": "DDC",
      "target_class": "CONTROL_PANEL",
      "relation_type": "mounted_on",
      "max_distance": 100,
      "min_confidence": 0.6,
      "priority": 10,
      "enabled": true
    }
  ]
}
```

### Required Behavior

The rule seeder should:

- Read UTF-8 JSON.
- Validate that top-level `rules` exists and is a list.
- Convert each entry to `RuleTemplateInput`.
- Use existing `seed_rules()` behavior to avoid duplicates by rule name.
- Return/print a concise summary: total, created/skipped if practical, errors.
- Preserve rule fields: name, source_class, target_class, relation_type, version, rule_kind, max_distance, expression, min_confidence, priority, enabled, config, valid_from, valid_to.

### Suggested Design

Create:

```text
dwg_rec_system/services/rules.py
```

Suggested API:

```python
class RuleTemplateSeeder:
    def __init__(self, connection): ...
    def seed_file(self, path: str | Path) -> dict: ...
    def seed_data(self, payload: dict) -> dict: ...
```

### Required Tests

Add tests for:

- rule JSON seeding creates a rule
- repeated seeding is idempotent
- missing `rules` raises a clear error
- imported sample objects + seeded sample rule + `infer-relations` creates one `mounted_on` relation

### Validation Commands

```powershell
python -m pytest -q
$env:DWG_REC_DB="data/round2_demo.db"
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json
python -m dwg_rec_system.cli seed-rules --input samples/demo_rules.json
python -m dwg_rec_system.cli infer-relations
```

Expected result: `infer-relations` returns one `mounted_on` relation for `DDC -> CONTROL_PANEL`.

## Agent B: Candidate Review CLI

### Objective

Add CLI commands to inspect and manage `relation_candidate` rows without direct SQL.

Required commands:

```powershell
python -m dwg_rec_system.cli list-candidates
python -m dwg_rec_system.cli accept-candidate <candidate_id>
python -m dwg_rec_system.cli reject-candidate <candidate_id>
```

Optional filters for `list-candidates`:

```powershell
--status pending|accepted|rejected|superseded
--source rule|llm|parser|import
--relation-type mounted_on
```

### Allowed Files

- `dwg_rec_system/cli.py`
- `dwg_rec_system/repositories.py`
- `dwg_rec_system/services/`
- `tests/`
- `README.md` only for command documentation

### Disallowed Changes

- Do not modify `schema.sql`.
- Do not remove automatic acceptance in current `RelationEngine` unless a separate architecture decision is made.
- Do not bypass `RelationCandidateRepository.accept()`.
- Do not write final `relation` rows directly from CLI.

### Required Behavior

`list-candidates` should:

- Return candidate rows as JSON.
- Include enough identifiers for review: candidate id, source id, target id, relation_type, confidence, source, status, rule_id, evidence_json.

`accept-candidate` should:

- Use `RelationCandidateRepository.accept(candidate_id)`.
- Return the created/updated relation id.

`reject-candidate` should:

- Set `relation_candidate.status = 'rejected'`.
- Update `updated_at`.
- Return a concise JSON summary.
- Not delete any candidate.
- Not delete existing relations. If a relation already exists from the rejected candidate, leave conflict handling for a later manual correction task.

### Suggested Design

Add methods to `RelationCandidateRepository`:

```python
def list(self, status: str | None = None, source: str | None = None, relation_type: str | None = None) -> list[dict]: ...
def reject(self, candidate_id: str) -> None: ...
```

### Required Tests

Add tests for:

- listing pending candidates
- accepting a candidate creates or updates a final relation
- rejecting a candidate changes status and does not delete the row
- CLI commands print valid JSON

### Validation Commands

```powershell
python -m pytest -q
python -m dwg_rec_system.cli list-candidates
```

## Agent C: Importer Strict Taxonomy Mode

### Objective

Add production-friendly taxonomy validation to `import-json`.

New CLI option:

```powershell
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json --strict-taxonomy
```

### Allowed Files

- `dwg_rec_system/importers/normalized_json.py`
- `dwg_rec_system/cli.py`
- `tests/`
- `docs/import_format.md`
- `README.md` only for command documentation

### Disallowed Changes

- Do not modify `schema.sql`.
- Do not change the `source_file + handle` identity rule.
- Do not make strict mode the only mode. Non-strict mode must remain available for exploratory imports.
- Do not silently create unknown classes in strict mode.

### Current Issue To Fix

Current importer behavior resolves class IDs with:

```text
object_class.code == class_name
```

but if the class does not exist it creates a new `object_class` entry. That is convenient for prototypes but unsafe for production.

### Required Behavior

Non-strict mode:

- Keep current behavior or equivalent: unknown classes may be imported.
- If auto-creating unknown classes, make this explicit in the summary if practical.

Strict mode:

- Unknown `class_name` must be reported as an import error.
- No `cad_object` should be created for that invalid object.
- Prefer fail-fast for malformed input, but per-object errors are acceptable if the summary clearly reports them and valid objects still import.

### Suggested Design

Update constructor:

```python
class NormalizedJsonImporter:
    def __init__(self, connection, strict_taxonomy: bool = False): ...
```

Use a private lookup helper:

```python
def _find_class_id(self, class_name: str) -> str | None: ...
```

Avoid `get_or_create()` in strict lookup.

### Required Tests

Add tests for:

- strict mode succeeds after `seed-taxonomy` when class exists
- strict mode rejects unknown class
- non-strict mode still imports unknown class
- CLI `--strict-taxonomy` works

### Validation Commands

```powershell
python -m pytest -q
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json --strict-taxonomy
```

## Agent D: Documentation And End-To-End Demo

### Objective

Update docs and README so the demo workflow is accurate and produces a relation.

### Allowed Files

- `README.md`
- `docs/import_format.md`
- `docs/development_plan.md`
- `docs/agent_tasks_round_2.md` only for clarifying comments
- `samples/demo_rules.json`

### Disallowed Changes

- Do not change production code.
- Do not change tests unless a sample file must align with test expectations.

### Required Documentation Updates

README must show this complete workflow:

```powershell
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json --strict-taxonomy
python -m dwg_rec_system.cli seed-rules --input samples/demo_rules.json
python -m dwg_rec_system.cli infer-relations
python -m dwg_rec_system.cli export-csv
```

Clarify:

- `import-json` imports normalized parser output; it is not a DWG parser.
- `seed-rules` is required before `infer-relations` can infer from imported objects.
- `--strict-taxonomy` is recommended after taxonomy has been seeded.
- Current `RelationEngine` accepts rule candidates immediately; richer manual review comes through candidate CLI and later workflow work.

### Required Validation

Run the documented commands on a temporary database and confirm:

- two objects are imported
- one rule is seeded
- one relation is inferred
- CSV export succeeds

## Suggested Round 2 Merge Order

1. Agent A: Rule Template Importer
2. Agent C: Importer Strict Taxonomy Mode
3. Agent B: Candidate Review CLI
4. Agent D: Documentation And End-To-End Demo

Agent C can run before Agent A if it avoids touching the same `cli.py` sections. Agent D should run last.

## Final Round 2 Acceptance

Round 2 is complete when the following works from a clean temporary database:

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

Expected:

- taxonomy seeding imports 164 object classes
- JSON import creates 2 objects
- repeated JSON import updates the same 2 objects
- rule seeding creates or skips 1 rule idempotently
- relation inference produces a `mounted_on` relation
- candidate listing returns the accepted rule candidate
- tests pass
