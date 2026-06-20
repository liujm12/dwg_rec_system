# CAD/DWG Recognition Data Foundation

This repository is a local-deployable engineering data foundation for CAD/DWG recognition results.

It is not a direct DWG-to-Excel script. The intended flow is:

```text
CAD/DWG/DXF/parser output
  -> normalized JSON
  -> ObjectStore
  -> cad_object + geometry + cad_meta + attribute
  -> relation_candidate
  -> accepted relation
  -> quantity_item
  -> data quality findings
  -> budget_item
  -> install_task + install_dependency + install_instruction
  -> exports and future engineering deliverables
```

The long-term roadmap covers multi-discipline equipment recognition, quantity takeoff, budgeting, installation guidance, and installation workflow planning. See `docs/final_roadmap.md`.

## Core Concepts

- `cad_object` is the universal object table for equipment, rooms, pipes, ducts, cable trays, valves, labels, dimensions, and annotations.
- `geometry`, `cad_meta`, and `attribute` are stored separately from `cad_object`.
- `attribute` uses a flexible EAV model for discipline-specific fields such as tag, model, diameter, voltage, airflow, and material.
- Inference writes to `relation_candidate` first.
- Accepted engineering truth is stored in `relation`.
- Human correction and review should remain auditable through correction records.

## Current Capabilities

- SQLite schema for projects, drawings, objects, geometry, CAD metadata, attributes, rules, candidates, relations, corrections, and artifacts.
- Normalized JSON importer for parser-agnostic CAD recognition output.
- Idempotent object import by `source_file + handle`.
- Taxonomy seeding from `dwg_rec_system/taxonomy/cad_object_taxonomy.json`.
- Engineering class profiles from `dwg_rec_system/taxonomy/engineering_class_profiles.json`.
- Rule template seeding from JSON.
- Rule-based relation inference through `relation_candidate -> relation`.
- Candidate review CLI for listing, accepting, and rejecting relation candidates.
- Quantity takeoff into durable `quantity_item` rows from engineering profiles, geometry, and attributes.
- Data quality checks for missing attributes, missing geometry, low confidence, manual-review quantities, missing profiles, and missing accepted relations.
- Budget generation from `quantity_item` and seeded `cost_item` rows.
- Installation guidance from accepted objects, accepted relations, and `engineering_class_profiles.json` installation profiles.
- Spatial queries for nearest, contains, and overlap.
- CSV export for recognized objects, quantity rows, data quality findings, budget rows, and installation tasks.

## Quick Start

Run from the repository root:

```powershell
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json --strict-taxonomy
python -m dwg_rec_system.cli seed-rules --input samples/demo_rules.json
python -m dwg_rec_system.cli infer-relations
python -m dwg_rec_system.cli list-candidates
python -m dwg_rec_system.cli generate-quantities
python -m dwg_rec_system.cli list-quantities
python -m dwg_rec_system.cli check-data-quality
python -m dwg_rec_system.cli list-quality-findings
python -m dwg_rec_system.cli seed-cost-items --input samples/demo_cost_items.json
python -m dwg_rec_system.cli generate-budget
python -m dwg_rec_system.cli list-budget-items
python -m dwg_rec_system.cli generate-install-tasks
python -m dwg_rec_system.cli generate-install-dependencies
python -m dwg_rec_system.cli generate-install-instructions
python -m dwg_rec_system.cli list-install-tasks
python -m dwg_rec_system.cli list-install-dependencies
python -m dwg_rec_system.cli list-install-instructions
python -m dwg_rec_system.cli export-csv
python -m dwg_rec_system.cli export-quantities-csv
python -m dwg_rec_system.cli export-quality-findings-csv
python -m dwg_rec_system.cli export-budget-csv
python -m dwg_rec_system.cli export-install-tasks-csv
```

Expected result:

- taxonomy seeding imports the CAD object classes
- JSON import creates the demo control panel and DDC objects
- rule seeding creates or skips one `mounted_on` rule
- relation inference creates one accepted candidate and one final relation
- quantity generation creates auditable `quantity_item` rows from `engineering_class_profiles.json`
- data quality checks produce reviewable findings before budgeting
- cost item seeding creates demo BMS price rules
- budget generation creates auditable `budget_item` rows
- installation task generation creates auditable `install_task` rows from profiled objects
- accepted relations generate simple `install_dependency` hints when both sides have tasks
- installation instruction generation creates deterministic template text in `install_instruction`
- CSV export writes `exports/objects.csv`
- quantity CSV export writes `exports/quantities.csv`
- quality CSV export writes `exports/quality_findings.csv`
- budget CSV export writes `exports/budget.csv`
- installation task CSV export writes `exports/install_tasks.csv`

## Important Notes

`import-json` imports normalized parser output. It is not a DWG parser.

`seed-rules` is required before `infer-relations` can infer relations from objects imported through `import-json`.

`--strict-taxonomy` is recommended after running `seed-taxonomy`. It rejects objects whose `class_name` is not present in `object_class`.

Without `--strict-taxonomy`, unknown classes are allowed and are auto-created for exploratory imports.

The current `RelationEngine` accepts rule candidates immediately after creating them. Manual review workflows are exposed through candidate CLI commands and can become richer in later milestones.

`generate-quantities` is not a budget generator. It creates auditable quantity rows that later budget services can price. Unsupported formula methods and missing geometry produce `manual_review` quantity rows with evidence explaining the reason.

`check-data-quality` is not a durable review database. Round 5 recomputes findings from current objects, quantities, relations, and engineering profiles, then prints JSON or exports CSV. Budget generation should wait until findings are reviewed or accepted as known risk.

`generate-budget` is deterministic prototype budgeting. It matches active cost items by `class_code` and `unit`, calculates material/labor/machine/total costs, and creates unmatched rows when no cost item can price a quantity. It does not mutate `quantity_item`.

`generate-install-tasks` is deterministic installation guidance, not workflow planning. It creates one project-specific `install_task` for each active object with an installation profile. `generate-install-dependencies` uses only accepted `relation` rows for simple dependency hints. `generate-install-instructions` creates template text from structured task evidence; it is not LLM-generated.

## CLI Commands

| Command | Description |
| --- | --- |
| `init-db` | Create or update the SQLite schema. |
| `seed-taxonomy` | Seed `object_class` from the bundled taxonomy JSON. |
| `import-json --input <file>` | Import normalized CAD parser JSON. |
| `import-json --input <file> --strict-taxonomy` | Import only objects whose classes already exist in taxonomy. |
| `seed-rules --input <file>` | Seed rule templates from JSON. |
| `list-objects [--class-name <class>]` | List recognized objects. |
| `nearest <object_id> [--target-class <class>] [--limit N]` | Find nearest objects by center point. |
| `infer-relations` | Run rule-based relation inference. |
| `list-candidates` | List relation candidates. |
| `list-candidates --status accepted` | Filter candidates by status. |
| `accept-candidate <candidate_id>` | Accept a relation candidate into final `relation`. |
| `reject-candidate <candidate_id>` | Mark a relation candidate as rejected. |
| `export-csv [--output <file>]` | Export recognized objects to CSV. |
| `generate-quantities [--project-id <id>] [--drawing-id <id>]` | Generate `quantity_item` rows from objects and engineering profiles. |
| `list-quantities [--class-code <class>] [--status <status>]` | List generated quantity rows as JSON. |
| `export-quantities-csv [--output <file>]` | Export quantity rows to CSV. |
| `check-data-quality [--low-confidence-threshold N]` | Recompute data quality findings and print summary plus findings. |
| `list-quality-findings [--severity <level>] [--category <category>]` | Recompute and list filtered findings as JSON. |
| `export-quality-findings-csv [--output <file>]` | Recompute and export findings to CSV. |
| `seed-cost-items --input <file>` | Seed cost library rows from JSON. |
| `list-cost-items [--class-code <class>] [--status active]` | List cost library rows as JSON. |
| `generate-budget [--project-id <id>] [--drawing-id <id>]` | Generate `budget_item` rows from quantity rows and cost items. |
| `list-budget-items [--status <status>]` | List generated budget rows as JSON. |
| `export-budget-csv [--output <file>]` | Export budget rows to CSV. |
| `generate-install-tasks [--project-id <id>] [--drawing-id <id>]` | Generate `install_task` rows from objects and installation profiles. |
| `generate-install-dependencies [--project-id <id>] [--drawing-id <id>]` | Generate simple `install_dependency` rows from accepted relations. |
| `generate-install-instructions [--project-id <id>] [--drawing-id <id>]` | Generate deterministic installation instruction text. |
| `list-install-tasks [--class-code <class>] [--status <status>]` | List installation tasks as JSON. |
| `list-install-dependencies [--status <status>]` | List installation dependencies as JSON. |
| `list-install-instructions [--task-id <id>]` | List generated installation instructions as JSON. |
| `export-install-tasks-csv [--output <file>]` | Export installation tasks to CSV. |

## Sample Files

- `samples/demo_parsed.json`: normalized parser output with one control panel and one DDC controller.
- `samples/demo_rules.json`: one spatial rule that infers `DDC mounted_on CONTROL_PANEL`.
- `samples/demo_cost_items.json`: demo cost item library for CONTROL_PANEL and DDC quantities.
- `dwg_rec_system/taxonomy/cad_object_taxonomy.json`: primary CAD object taxonomy and the source for `object_class`.
- `dwg_rec_system/taxonomy/engineering_class_profiles.json`: engineering profile overlay used by quantity generation and future budget/installation services.

## Tests

```powershell
python -m pytest -q
```

## Database Path

The default database path is:

```text
data/dwg_rec_system.db
```

Override it with `DWG_REC_DB`:

```powershell
$env:DWG_REC_DB="data/round2_demo.db"
python -m dwg_rec_system.cli init-db
```

## Roadmap

- `docs/development_plan.md`: staged development plan.
- `docs/agent_tasks_round_1.md`: completed normalized import foundation tasks.
- `docs/agent_tasks_round_2.md`: rule and candidate workflow task package.
- `docs/agent_tasks_round_3.md`: completed multi-discipline taxonomy profile task package.
- `docs/agent_tasks_round_4.md`: completed quantity takeoff task package.
- `docs/agent_tasks_round_5.md`: completed data quality gate task package.
- `docs/agent_tasks_round_6.md`: completed budgeting task package.
- `docs/agent_tasks_round_7.md`: completed installation guidance task package.
- `docs/taxonomy_profile.md`: taxonomy profile shape and usage guide.
- `docs/final_roadmap.md`: long-term database and module roadmap for multi-discipline budgeting and installation planning.
