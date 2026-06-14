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
- Spatial queries for nearest, contains, and overlap.
- CSV export for recognized objects.

## Quick Start

Run from the repository root:

```powershell
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json --strict-taxonomy
python -m dwg_rec_system.cli seed-rules --input samples/demo_rules.json
python -m dwg_rec_system.cli infer-relations
python -m dwg_rec_system.cli list-candidates
python -m dwg_rec_system.cli export-csv
```

Expected result:

- taxonomy seeding imports the CAD object classes
- JSON import creates the demo control panel and DDC objects
- rule seeding creates or skips one `mounted_on` rule
- relation inference creates one accepted candidate and one final relation
- CSV export writes `exports/objects.csv`

## Important Notes

`import-json` imports normalized parser output. It is not a DWG parser.

`seed-rules` is required before `infer-relations` can infer relations from objects imported through `import-json`.

`--strict-taxonomy` is recommended after running `seed-taxonomy`. It rejects objects whose `class_name` is not present in `object_class`.

Without `--strict-taxonomy`, unknown classes are allowed and are auto-created for exploratory imports.

The current `RelationEngine` accepts rule candidates immediately after creating them. Manual review workflows are exposed through candidate CLI commands and can become richer in later milestones.

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

## Sample Files

- `samples/demo_parsed.json`: normalized parser output with one control panel and one DDC controller.
- `samples/demo_rules.json`: one spatial rule that infers `DDC mounted_on CONTROL_PANEL`.
- `dwg_rec_system/taxonomy/cad_object_taxonomy.json`: primary CAD object taxonomy and the source for `object_class`.
- `dwg_rec_system/taxonomy/engineering_class_profiles.json`: Round 3 engineering profile overlay for future quantity, budget, and installation services.

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
- `docs/taxonomy_profile.md`: taxonomy profile shape and usage guide.
- `docs/final_roadmap.md`: long-term database and module roadmap for multi-discipline budgeting and installation planning.
