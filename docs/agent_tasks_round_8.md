# Agent Tasks Round 8

Round 8 turns generated installation tasks and simple dependencies into a reviewable workflow planning layer.

Round 7 provided:

```text
cad_object + relation + engineering_class_profiles.json
  -> install_task
  -> install_dependency
  -> install_instruction
```

Round 8 should make this work:

```text
seed-taxonomy
  -> import-json --strict-taxonomy
  -> seed-rules
  -> infer-relations
  -> generate-install-tasks
  -> generate-install-dependencies
  -> generate-install-instructions
  -> generate-workflow-plan
  -> list-workflow-steps
  -> list-workflow-issues
  -> export-workflow-plan-csv
```

## Round Goal

Implement the first workflow planning layer on top of Round 7 installation guidance.

The output of Round 8 is not a full construction schedule, Gantt chart, crew optimizer, critical-path optimizer, API, UI, real parser, or LLM feature. It is an auditable planning layer that records:

- which installation tasks were included in a workflow plan
- how tasks were grouped by project, drawing, discipline, work package, location, and system
- which dependencies influenced the recommended order
- which tasks are blocked or need review because dependency evidence is missing, cyclic, rejected, or incomplete
- what deterministic sequence order is recommended for review

Round 8 should answer questions like:

```text
Which installation tasks are ready to plan?
What order does the existing dependency graph imply?
Which dependencies block a task?
Which tasks need review before installation sequencing can be trusted?
Can the workflow plan be exported for engineering review?
```

## Coordination Rules

- Every agent must read `CLAUDE.md`, `docs/architecture.md`, `docs/final_roadmap.md`, `docs/development_plan.md`, `docs/taxonomy_profile.md`, `docs/agent_tasks_round_6.md`, `docs/agent_tasks_round_7.md`, and this file.
- Every agent must run `python -m pytest -q`.
- Do not implement real crew/resource allocation in Round 8.
- Do not implement Gantt charts, calendars, shift planning, procurement planning, or critical-path optimization.
- Do not implement DWG/DXF/PDF parsing, API, UI, web services, or LLM behavior.
- Do not add external dependencies.
- Keep object import through `ObjectStore`.
- Keep relation uncertainty flow as `relation_candidate -> relation`.
- Use only `install_task` and accepted/non-rejected `install_dependency` rows as workflow inputs.
- Do not mutate `cad_object`, `quantity_item`, `budget_item`, or installation instruction text when generating workflow records.
- Prefer deterministic logic and explicit evidence over hidden heuristics.

## Schema Boundary

Round 8 is an explicit architecture task for workflow planning tables.

Allowed schema additions:

```text
workflow_plan
workflow_step
workflow_issue
```

Do not add schedule optimization tables in Round 8.

Do not modify existing core table semantics:

- `cad_object`
- `geometry`
- `cad_meta`
- `attribute`
- `relation_candidate`
- `relation`
- `quantity_item`
- `budget_item`
- `install_task`
- `install_dependency`
- `install_instruction`

Do not add fields to `install_task` unless absolutely necessary. Workflow status should live in workflow tables.

## Workflow Plan Contract

`workflow_plan` stores one generated planning run for a selected project/drawing scope.

Suggested fields:

```text
id
project_id
drawing_id
name
scope_json
generator
generator_version
status
summary_json
created_at
updated_at
```

Suggested `status` values:

```text
draft
review
ready
superseded
rejected
```

Recommended semantics:

- A plan is generated from current `install_task` and `install_dependency` rows.
- Regeneration should create a new plan and mark previous generated draft/review plans in the same scope as `superseded`, or clear only auto-generated child rows if the implementation keeps one current plan. Pick one approach and document it.
- `scope_json` should preserve filters such as project, drawing, discipline, work package, location, and system.
- `summary_json` should include counts for tasks, planned steps, blocked steps, review steps, issues, and cycles.

## Workflow Step Contract

`workflow_step` stores deterministic ordered rows inside a workflow plan.

Suggested fields:

```text
id
plan_id
task_id
sequence_no
sequence_group
discipline
work_package
location
system_code
dependency_count
blocked_by_count
status
evidence_json
created_at
updated_at
```

Suggested `status` values:

```text
planned
review
blocked
unplanned
done
rejected
```

Recommended semantics:

- One workflow step per included `install_task`.
- `sequence_no` should be deterministic.
- `sequence_group` can be a stable grouping key such as `discipline|work_package|location|system`.
- Tasks with review installation status, review dependencies, missing prerequisites, or cycle involvement should become `review` or `blocked`.
- Evidence should include task id, dependency ids used, predecessor task ids, successor task ids, and ordering method.

## Workflow Issue Contract

`workflow_issue` stores reviewable planning problems.

Suggested fields:

```text
id
plan_id
task_id
dependency_id
severity
category
code
message
evidence_json
status
created_at
updated_at
```

Suggested `severity` values:

```text
error
warning
info
```

Suggested `category` values:

```text
cycle
missing_dependency_task
review_dependency
blocked_predecessor
unplanned_task
task_needs_review
missing_scope
```

Suggested `status` values:

```text
open
accepted
resolved
rejected
```

Recommended semantics:

- Cycle issues should be `error`.
- Missing predecessor/successor task issues should be `error` or `warning` depending on whether the dependency can be ignored safely.
- Review dependencies should be `warning`.
- Tasks already marked `review` in `install_task` should create `task_needs_review` issues.

## Workflow Generation Semantics

### Task Loading

Read active installation tasks:

- include `install_task.status IN ('auto', 'review', 'ready', 'blocked', 'corrected')`
- exclude `install_task.status IN ('rejected', 'done')` by default
- support filters:
  - `project_id`
  - `drawing_id`
  - `discipline`
  - `work_package`
  - `location`
  - `system_code`

### Dependency Loading

Read workflow-relevant dependencies:

- include dependencies whose predecessor and successor tasks are both in scope
- include dependency statuses `auto`, `review`, and `corrected`
- exclude `rejected`
- keep review dependencies visible as review issues
- record skipped out-of-scope dependency evidence in `workflow_issue` when useful

### Ordering

Round 8 should implement deterministic topological ordering, not schedule optimization.

Recommended ordering behavior:

1. Build a directed graph from `install_dependency.predecessor_task_id -> successor_task_id`.
2. Topologically sort tasks where possible.
3. Break ties deterministically by:
   - discipline
   - work package
   - location
   - system code
   - class code
   - task name
   - task id
4. If cycles exist, emit `workflow_issue` rows and put cycle-involved tasks after acyclic planned tasks with status `blocked` or `review`.
5. Do not calculate durations, dates, manpower, or critical path.

### Status Rules

Suggested step status:

- `planned`: task has no review/blocking issues.
- `review`: task is plan-able but has review dependency or source task status `review`.
- `blocked`: task is involved in a cycle or has a missing/rejected predecessor that prevents deterministic ordering.
- `unplanned`: task was in scope but could not be placed for a reason other than cycle.

Plan status:

- `ready`: no error issues and no blocked steps.
- `review`: warning issues exist or review steps exist.
- `draft`: generation succeeded but plan has not been reviewed.

The implementation can choose `review` as the default generated status if that better matches audit-first behavior, but it must be deterministic and documented.

## Agent A: Workflow Schema And Repositories

### Objective

Add schema and repository support for workflow plans, workflow steps, and workflow issues.

### Allowed Files

- `dwg_rec_system/schema.sql`
- `dwg_rec_system/db.py`
- `dwg_rec_system/repositories.py`
- `tests/`
- `docs/` only for clarifying behavior

### Disallowed Changes

- Do not modify existing core or installation table semantics.
- Do not add schedule optimization tables.
- Do not add parser, API, UI, or LLM behavior.
- Do not add external dependencies.

### Required Behavior

Add schema for:

```text
workflow_plan
workflow_step
workflow_issue
```

Update SQLite compatibility setup in `dwg_rec_system/db.py` for existing local databases.

Add repositories such as:

```python
class WorkflowPlanRepository:
    def create(...): ...
    def mark_superseded(...): ...
    def list(...): ...

class WorkflowStepRepository:
    def create(...): ...
    def clear_for_plan(...): ...
    def list(...): ...

class WorkflowIssueRepository:
    def create(...): ...
    def clear_for_plan(...): ...
    def list(...): ...
```

Suggested behavior:

- JSON fields should be stored as text.
- `list` should support filters:
  - `project_id`
  - `drawing_id`
  - `plan_id`
  - `status`
  - `severity`
  - `category`
  - `task_id`
- Regeneration should not delete manually reviewed historical plans unless explicitly requested.

### Required Tests

Add tests for:

- workflow tables exist with expected columns
- plan creation and listing
- step creation and listing
- issue creation and listing
- superseding old generated plans
- JSON evidence/source fields are stored and readable

### Validation Commands

```powershell
python -m pytest -q
```

## Agent B: Workflow Graph Service

### Objective

Build a deterministic workflow graph from installation tasks and dependencies.

### Allowed Files

- `dwg_rec_system/services/`
- `dwg_rec_system/repositories.py`
- `tests/`
- `docs/` only for clarifying behavior

### Disallowed Changes

- Do not implement schedule optimization.
- Do not implement resource allocation.
- Do not mutate install tasks or dependencies.
- Do not infer new object relations.
- Do not use LLMs or external dependencies.

### Required Behavior

Create or extend:

```text
dwg_rec_system/services/workflow.py
```

Suggested API:

```python
class WorkflowGraphBuilder:
    def __init__(self, connection): ...

    def build(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
        discipline: str | None = None,
        work_package: str | None = None,
        location: str | None = None,
        system_code: str | None = None,
    ) -> dict: ...
```

The builder should:

- load installation tasks in scope
- load dependencies between scoped tasks
- build predecessor/successor maps
- detect missing predecessor/successor task references
- detect review dependencies
- detect cycles
- return a structured graph object that the plan generator can consume

Suggested return shape:

```json
{
  "tasks": [],
  "dependencies": [],
  "predecessors": {},
  "successors": {},
  "issues": [],
  "cycles": []
}
```

### Required Tests

Add tests for:

- graph includes scoped tasks
- graph includes dependency edges between scoped tasks
- out-of-scope dependencies are skipped or reported deterministically
- review dependencies create warning issues
- rejected dependencies are ignored
- cycles are detected

### Validation Commands

```powershell
python -m pytest -q
```

## Agent C: Workflow Plan Generator

### Objective

Generate a durable workflow plan with deterministic workflow steps and issues.

### Allowed Files

- `dwg_rec_system/services/`
- `dwg_rec_system/repositories.py`
- `tests/`
- `docs/` only for clarifying behavior

### Disallowed Changes

- Do not calculate dates, durations, critical path, float, or manpower.
- Do not modify install tasks or dependencies.
- Do not create Gantt output.
- Do not use LLMs or external dependencies.

### Required Behavior

Suggested API:

```python
class WorkflowPlanGenerator:
    def __init__(self, connection): ...

    def generate(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
        discipline: str | None = None,
        work_package: str | None = None,
        location: str | None = None,
        system_code: str | None = None,
        name: str | None = None,
    ) -> dict: ...
```

The generator should:

- call `WorkflowGraphBuilder`
- create a `workflow_plan`
- topologically order tasks where possible
- create one `workflow_step` per scoped task
- create `workflow_issue` rows for graph and task review issues
- write summary counts to `workflow_plan.summary_json`
- return a JSON summary:

```json
{
  "plan_id": "",
  "tasks_total": 0,
  "steps_created": 0,
  "issues_created": 0,
  "blocked_steps": 0,
  "review_steps": 0,
  "cycles": 0,
  "status": "review"
}
```

### Required Tests

Add tests for:

- simple chain produces ordered sequence numbers
- branching dependencies produce deterministic tie ordering
- disconnected tasks are included deterministically
- cycles create issues and blocked/review steps
- install task `review` status creates a workflow issue
- repeated generation creates a new plan or supersedes the old one according to the documented policy
- filters limit the plan scope

### Validation Commands

```powershell
python -m pytest -q
```

## Agent D: Workflow CLI And Export

### Objective

Expose workflow planning through CLI and CSV export.

### Required Commands

```powershell
python -m dwg_rec_system.cli generate-workflow-plan
python -m dwg_rec_system.cli list-workflow-plans
python -m dwg_rec_system.cli list-workflow-steps
python -m dwg_rec_system.cli list-workflow-issues
python -m dwg_rec_system.cli export-workflow-plan-csv
```

Optional filters:

```powershell
generate-workflow-plan --project-id <id> --drawing-id <id>
generate-workflow-plan --discipline BMS --work-package "control equipment installation"
list-workflow-steps --plan-id <id>
list-workflow-issues --plan-id <id> --severity warning
export-workflow-plan-csv --plan-id <id> --output exports/workflow_plan.csv
```

### Allowed Files

- `dwg_rec_system/cli.py`
- `dwg_rec_system/services/`
- `dwg_rec_system/repositories.py`
- `tests/`
- `README.md`
- `docs/`

### Disallowed Changes

- Do not implement Excel export in Round 8 unless already trivial from existing code.
- Do not implement API, UI, Gantt output, or LLM behavior.
- Do not modify object import behavior.
- Do not add external dependencies.

### Required Behavior

`generate-workflow-plan` should:

- run `WorkflowPlanGenerator`
- print JSON summary
- support project/drawing/discipline/work_package/location/system filters

`list-workflow-plans` should:

- print plan rows as JSON
- support project/drawing/status filters

`list-workflow-steps` should:

- print step rows as JSON
- support plan/status/task filters

`list-workflow-issues` should:

- print issue rows as JSON
- support plan/severity/category/status/task filters

`export-workflow-plan-csv` should:

- default to `exports/workflow_plan.csv`
- export ordered workflow steps
- include enough fields for review:
  - plan_id
  - sequence_no
  - sequence_group
  - task_id
  - task_name
  - class_code
  - discipline
  - work_package
  - location
  - system_code
  - dependency_count
  - blocked_by_count
  - status

### Required Tests

Add tests for:

- CLI commands print valid JSON where expected
- full command flow works after sample import, relation inference, and Round 7 generation
- CSV export writes expected headers
- filters work

### Validation Commands

```powershell
python -m pytest -q
```

## Agent E: Documentation And Acceptance

### Objective

Document the workflow planning layer and update the development plan after implementation lands.

### Allowed Files

- `README.md`
- `docs/development_plan.md`
- `docs/final_roadmap.md`
- `docs/agent_tasks_round_8.md`
- `samples/` only if a sample import/rule file needs workflow examples

### Disallowed Changes

- Do not modify production code.
- Do not add parser, API, UI, Gantt output, schedule optimization, or LLM behavior.

### Required Documentation

Update docs to explain:

- Round 8 generates reviewable workflow plans from Round 7 installation tasks and dependencies
- Round 8 does not generate a calendar schedule, Gantt chart, or optimized crew plan
- `workflow_plan` is a generated planning run
- `workflow_step` is a deterministic ordered task row
- `workflow_issue` is a reviewable problem found while planning
- accepted relations and installation dependencies improve workflow quality
- missing or review dependencies should remain visible as workflow issues

After implementation lands:

- mark Milestone 8 as complete
- set Milestone 9 Recognition Modeling Layer as next

### Validation Commands

```powershell
python -m pytest -q
```

## Final Round 8 Acceptance

Round 8 is complete when this works from a clean temporary database:

```powershell
python -m pytest -q
$env:DWG_REC_DB="data/round8_acceptance.db"
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json --strict-taxonomy
python -m dwg_rec_system.cli seed-rules --input samples/demo_rules.json
python -m dwg_rec_system.cli infer-relations
python -m dwg_rec_system.cli generate-install-tasks
python -m dwg_rec_system.cli generate-install-dependencies
python -m dwg_rec_system.cli generate-install-instructions
python -m dwg_rec_system.cli generate-workflow-plan
python -m dwg_rec_system.cli list-workflow-plans
python -m dwg_rec_system.cli list-workflow-steps
python -m dwg_rec_system.cli list-workflow-issues
python -m dwg_rec_system.cli export-workflow-plan-csv
```

Expected:

- tests pass
- `workflow_plan`, `workflow_step`, and `workflow_issue` exist
- demo installation tasks generate a workflow plan
- accepted installation dependencies influence step order
- workflow issues are generated for review dependencies, review tasks, cycles, or missing dependency evidence when present
- CSV export succeeds
- no Gantt chart, calendar schedule, critical-path optimizer, crew/resource allocation, parser adapters, API, UI, LLM behavior, web services, or external dependencies are added
