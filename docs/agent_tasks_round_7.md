# Agent Tasks Round 7

Round 7 turns accepted objects, relations, and engineering installation profiles into auditable installation guidance.

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

Round 6 provided:

```text
quantity_item + cost_item
  -> budget_item
```

Round 7 should make this work:

```text
seed-taxonomy
  -> import-json --strict-taxonomy
  -> infer-relations / accept-candidate
  -> check-data-quality
  -> generate-install-tasks
  -> list-install-tasks
  -> generate-install-instructions
  -> list-install-instructions
  -> export-install-tasks-csv
```

## Round Goal

Implement the first installation guidance workflow.

The output of Round 7 is not a full construction schedule, Gantt chart, crew optimizer, API, UI, real parser, or LLM feature. It is an auditable installation layer that records:

- which installation tasks were generated from accepted objects
- what installation profile produced each task
- which simple dependencies were generated from accepted relations or profile prerequisites
- what human-readable installation instruction text was generated from structured data

Round 7 should answer questions like:

```text
Which recognized objects should become installation tasks?
What work package and default steps apply to each task?
Which accepted relation or profile prerequisite explains a dependency?
Can installation tasks and guidance be exported for review?
```

## Coordination Rules

- Every agent must read `CLAUDE.md`, `docs/architecture.md`, `docs/final_roadmap.md`, `docs/taxonomy_profile.md`, `docs/agent_tasks_round_4.md`, `docs/agent_tasks_round_5.md`, `docs/agent_tasks_round_6.md`, and this file.
- Every agent must run `python -m pytest -q`.
- Do not implement workflow planning or schedule optimization in Round 7.
- Do not implement real crew/resource allocation in Round 7.
- Do not implement DWG/DXF/PDF parsing, API, UI, or LLM behavior.
- Do not add external dependencies.
- Keep object import through `ObjectStore`.
- Keep relation uncertainty flow as `relation_candidate -> relation`.
- Use only accepted `relation` rows for installation dependencies.
- Keep engineering profiles as configuration, not hard-coded class behavior.
- Do not mutate `quantity_item` or `budget_item` when generating installation records.

## Schema Boundary

Round 7 is an explicit architecture task for installation guidance tables.

Allowed schema additions:

```text
install_task
install_dependency
install_instruction
```

Do not add workflow planning tables in Round 7.

Do not modify existing core table semantics:

- `cad_object`
- `geometry`
- `cad_meta`
- `attribute`
- `relation_candidate`
- `relation`
- `quantity_item`
- `budget_item`

`install_template` may remain implicit in `engineering_class_profiles.json` for Round 7. Add a durable `install_template` table only in a later round if repeated use proves the shape.

## Installation Profile Source

Round 7 should use `engineering_class_profiles.json`.

Relevant profile fields:

```text
code
profile_group
expected_attributes
relations
installation.work_package
installation.default_steps
installation.required_predecessors
```

Objects without an installation profile should be skipped by default and counted in the summary.

Installation generation must not hard-code class-specific behavior such as special cases for `DDC`, `VALVE`, or `CONTROL_PANEL` when profile data can drive the behavior.

## Install Task Contract

`install_task` stores project-specific installation work generated from accepted objects.

Suggested fields:

```text
id
project_id
drawing_id
object_id
class_code
discipline
task_name
work_package
location
system_code
priority
estimated_duration
crew_type
source
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
ready
blocked
corrected
rejected
done
```

Recommended semantics:

- One task per object for each object with a valid installation profile.
- `task_name` should be deterministic, such as `"Install CONTROL_PANEL"` or profile work package plus object tag when available.
- `work_package` should come from `installation.work_package`.
- `location` can come from object attribute `location`, `room_no`, or an accepted `located_in` relation if available.
- `system_code` can come from object attribute `system`.
- `confidence` should start from `cad_object.confidence`.
- Evidence should include source object id, class code, profile group, installation profile fields used, and selected attributes.

## Install Dependency Contract

`install_dependency` stores simple dependencies between generated installation tasks.

Suggested fields:

```text
id
predecessor_task_id
successor_task_id
dependency_type
reason
source
confidence
evidence_json
status
created_at
updated_at
```

Suggested `dependency_type` values:

```text
finish_to_start
start_to_start
inspection_before
pressure_test_before
power_before_commissioning
profile_prerequisite
```

Suggested `status` values:

```text
auto
review
corrected
rejected
```

Round 7 dependency scope should remain simple:

- Generate task-to-task dependencies only when both tasks exist.
- Use accepted relations to create obvious dependencies.
- Preserve profile prerequisite names in evidence even when no predecessor task exists.
- Do not implement topological sorting, schedule sequencing, critical path, or conflict resolution in Round 7. That is Round 8.

Suggested accepted relation mappings:

```text
mounted_on: target task before source task
installed_on: target task before source task
powered_by: target task before source task
controlled_by: target task before source task
connected_to: review dependency between connected tasks
located_in: location evidence only by default
```

## Install Instruction Contract

`install_instruction` stores readable guidance generated from structured task and profile data.

Suggested fields:

```text
id
task_id
instruction_text
generator
generator_version
source_json
created_at
```

Round 7 instructions should be deterministic template text, not LLM-generated text.

Suggested instruction content:

```text
task name
class code
work package
location/system if available
default steps from profile
dependency notes if available
review notes for missing required data
```

## Installation Generation Semantics

### Task Generation

For each active object:

- find profile by `cad_object.class`
- require `installation.work_package`
- create one `install_task`
- include default steps in evidence
- set status:
  - `auto` when confidence is acceptable and profile exists
  - `review` when object confidence is low or required installation profile fields are incomplete

Default low-confidence threshold:

```text
0.80
```

### Dependency Generation

After tasks are generated:

- read accepted active relations
- create dependencies only for relation mappings defined above
- skip dependencies when either side lacks a generated task
- keep dependencies deterministic and idempotent on regeneration

### Instruction Generation

For each install task:

- use profile default steps from task evidence when available
- include dependency notes from existing dependencies
- write one `install_instruction` per task
- regenerate by clearing previous auto-generated instructions for the selected scope

## Agent A: Installation Schema And Repositories

### Objective

Add schema and repository support for installation tasks, dependencies, and instructions.

### Allowed Files

- `dwg_rec_system/schema.sql`
- `dwg_rec_system/db.py`
- `dwg_rec_system/repositories.py`
- `tests/`
- `docs/` only for clarifying behavior

### Disallowed Changes

- Do not modify existing core table semantics.
- Do not add workflow planning tables.
- Do not add parser, API, UI, or LLM behavior.
- Do not add external dependencies.

### Required Behavior

Add schema for:

```text
install_task
install_dependency
install_instruction
```

Update SQLite compatibility setup in `dwg_rec_system/db.py` for existing local databases.

Add repositories such as:

```python
class InstallTaskRepository:
    def create(...): ...
    def clear_auto(...): ...
    def list(...): ...

class InstallDependencyRepository:
    def create(...): ...
    def clear_auto(...): ...
    def list(...): ...

class InstallInstructionRepository:
    def create(...): ...
    def clear_auto(...): ...
    def list(...): ...
```

Suggested behavior:

- `clear_auto` should delete auto/review generated rows but preserve corrected/rejected/done rows.
- `list` should support filters:
  - `project_id`
  - `drawing_id`
  - `class_code`
  - `status`
  - `task_id` for instructions
- Repositories should store evidence/source JSON as text.

### Required Tests

Add tests for:

- install tables exist with expected columns
- task creation and listing
- dependency creation and listing
- instruction creation and listing
- regeneration preserves corrected/rejected rows

### Validation Commands

```powershell
python -m pytest -q
```

## Agent B: Installation Task Service

### Objective

Generate installation tasks from recognized objects and engineering profiles.

### Allowed Files

- `dwg_rec_system/services/`
- `dwg_rec_system/repositories.py`
- `tests/`
- `docs/` only for clarifying behavior

### Disallowed Changes

- Do not implement schedule optimization.
- Do not implement installation dependencies beyond accepted relation/profile prerequisite evidence.
- Do not use LLMs or external dependencies.
- Do not mutate object, quantity, or budget rows.

### Required Behavior

Create:

```text
dwg_rec_system/services/installation.py
```

Suggested API:

```python
class InstallTaskGenerator:
    def __init__(
        self,
        connection,
        profile_path: str | Path | None = None,
        low_confidence_threshold: float = 0.8,
    ): ...

    def generate_tasks(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> dict: ...
```

The generator should:

- load `engineering_class_profiles.json`
- query objects, attributes, geometry, and accepted relations where useful
- create one task per profiled object
- skip objects without installation profile
- include profile default steps and required predecessors in evidence
- produce a summary:

```json
{
  "objects_total": 0,
  "created": 0,
  "skipped_no_profile": 0,
  "skipped_no_installation_profile": 0,
  "review": 0,
  "cleared": 0
}
```

### Required Tests

Add tests for:

- task generation from profile `installation.work_package`
- default steps preserved in evidence
- object attributes provide location/system
- low confidence object creates review task
- object without profile is skipped
- project/drawing filters
- repeated generation is idempotent for auto rows

### Validation Commands

```powershell
python -m pytest -q
```

## Agent C: Installation Dependency Service

### Objective

Generate simple install dependencies from accepted relations and generated tasks.

### Allowed Files

- `dwg_rec_system/services/`
- `dwg_rec_system/repositories.py`
- `tests/`
- `docs/` only for clarifying behavior

### Disallowed Changes

- Do not implement workflow sequencing or topological sorting.
- Do not infer new relation candidates.
- Do not create dependencies from unaccepted relation candidates.
- Do not use LLMs or external dependencies.

### Required Behavior

Suggested API:

```python
class InstallDependencyGenerator:
    def __init__(self, connection): ...
    def generate_dependencies(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> dict: ...
```

The generator should:

- read existing generated install tasks
- read accepted active `relation` rows
- map relation types to dependency directions
- create dependency rows only when both source and target tasks exist
- include relation id, relation type, source object id, and target object id in evidence
- return summary:

```json
{
  "relations_checked": 0,
  "created": 0,
  "skipped_missing_task": 0,
  "cleared": 0
}
```

### Required Tests

Add tests for:

- `mounted_on` creates target-before-source dependency
- `powered_by` creates target-before-source dependency
- `connected_to` creates review dependency
- unaccepted relation candidates are ignored
- dependencies are skipped when one task is missing
- repeated generation is idempotent for auto rows

### Validation Commands

```powershell
python -m pytest -q
```

## Agent D: Installation Instruction Service

### Objective

Generate deterministic human-readable installation instructions from tasks, dependencies, and profile evidence.

### Allowed Files

- `dwg_rec_system/services/`
- `dwg_rec_system/repositories.py`
- `tests/`
- `docs/` only for clarifying behavior

### Disallowed Changes

- Do not use LLMs.
- Do not create free-form instructions without structured source evidence.
- Do not implement workflow planning or optimized sequencing.

### Required Behavior

Suggested API:

```python
class InstallInstructionGenerator:
    def __init__(self, connection): ...
    def generate_instructions(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> dict: ...
```

The generator should:

- read install tasks
- read install dependencies for each task
- create one instruction per task
- include default profile steps from task evidence
- include dependency notes
- include review notes when task status is `review`
- return summary:

```json
{
  "tasks_total": 0,
  "created": 0,
  "cleared": 0
}
```

### Required Tests

Add tests for:

- instruction generation includes task name and work package
- default steps appear in instruction text
- dependencies appear in instruction text
- review status appears as review note
- repeated generation is idempotent for auto rows

### Validation Commands

```powershell
python -m pytest -q
```

## Agent E: Installation CLI And Export

### Objective

Expose installation task, dependency, and instruction workflows through CLI and CSV export.

### Required Commands

```powershell
python -m dwg_rec_system.cli generate-install-tasks
python -m dwg_rec_system.cli generate-install-dependencies
python -m dwg_rec_system.cli generate-install-instructions
python -m dwg_rec_system.cli list-install-tasks
python -m dwg_rec_system.cli list-install-dependencies
python -m dwg_rec_system.cli list-install-instructions
python -m dwg_rec_system.cli export-install-tasks-csv
```

Optional filters:

```powershell
generate-install-tasks --project-id <id> --drawing-id <id>
list-install-tasks --class-code CONTROL_PANEL --status review
list-install-instructions --task-id <id>
export-install-tasks-csv --output exports/install_tasks.csv
```

### Allowed Files

- `dwg_rec_system/cli.py`
- `dwg_rec_system/services/`
- `dwg_rec_system/repositories.py`
- `tests/`
- `README.md`
- `docs/`

### Disallowed Changes

- Do not implement Excel export in Round 7 unless already trivial from existing code.
- Do not implement installation API.
- Do not implement workflow planning.
- Do not modify object import behavior.
- Do not add external dependencies.

### Required Behavior

`generate-install-tasks` should:

- run `InstallTaskGenerator`
- print JSON summary

`generate-install-dependencies` should:

- run `InstallDependencyGenerator`
- print JSON summary

`generate-install-instructions` should:

- run `InstallInstructionGenerator`
- print JSON summary

`list-install-tasks` should:

- print task rows as JSON
- support project/drawing/class/status filters

`list-install-dependencies` should:

- print dependency rows as JSON
- support status filters

`list-install-instructions` should:

- print instruction rows as JSON
- support task id filters

`export-install-tasks-csv` should:

- write task rows to CSV
- default to `exports/install_tasks.csv`
- include enough fields for review:
  - object_id
  - class_code
  - discipline
  - task_name
  - work_package
  - location
  - system_code
  - priority
  - status
  - confidence

### Required Tests

Add tests for:

- CLI commands print valid JSON where expected
- full command flow works after sample import and accepted relation generation
- CSV export writes expected headers
- filters work

### Validation Commands

```powershell
python -m pytest -q
```

## Agent F: Documentation And Acceptance

### Objective

Document the installation guidance workflow and update the development plan after implementation lands.

### Allowed Files

- `README.md`
- `docs/development_plan.md`
- `docs/final_roadmap.md`
- `docs/agent_tasks_round_7.md`
- `samples/` only if a sample import/rule file needs installation examples

### Disallowed Changes

- Do not modify production code.
- Do not add workflow planning, parser, API, UI, or LLM behavior.

### Required Documentation

Update docs to explain:

- Round 7 generates installation tasks and deterministic instructions
- Round 7 does not generate a full installation schedule
- `install_task` is project-specific work derived from accepted objects and profiles
- `install_dependency` is simple relation-based prerequisite evidence, not an optimized workflow graph
- `install_instruction` is deterministic template text, not LLM text
- accepted relations improve dependency quality
- missing relations should still be reported by Round 5 data quality checks

After implementation lands:

- mark Milestone 7 as complete
- set Milestone 8 Workflow Planning as next

### Validation Commands

```powershell
python -m pytest -q
```

## Final Round 7 Acceptance

Round 7 is complete when this works from a clean temporary database:

```powershell
python -m pytest -q
$env:DWG_REC_DB="data/round7_acceptance.db"
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json --strict-taxonomy
python -m dwg_rec_system.cli seed-rules --input samples/demo_rules.json
python -m dwg_rec_system.cli infer-relations
python -m dwg_rec_system.cli generate-install-tasks
python -m dwg_rec_system.cli generate-install-dependencies
python -m dwg_rec_system.cli generate-install-instructions
python -m dwg_rec_system.cli list-install-tasks
python -m dwg_rec_system.cli list-install-dependencies
python -m dwg_rec_system.cli list-install-instructions
python -m dwg_rec_system.cli export-install-tasks-csv
```

Expected:

- tests pass
- `install_task`, `install_dependency`, and `install_instruction` exist
- profiled demo objects generate install tasks
- accepted relations can generate simple dependencies when both tasks exist
- instructions include profile default steps and dependency notes
- CSV export succeeds
- no workflow planning tables or optimized schedule outputs are created
- no parser adapters, API, UI, LLM behavior, web services, or external dependencies are added

