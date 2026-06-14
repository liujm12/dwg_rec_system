# Multi-Agent Development Guide

This repository is a CAD/DWG drawing recognition system foundation. Claude Code and DeepSeek sub-agents should treat this file as the primary operating guide for development work in this project.

## Project Goal

Build a local-deployable engineering data foundation that converts CAD/DWG recognition results into structured engineering objects, spatial data, attributes, candidate relations, accepted relations, and exportable artifacts.

The project is not a simple DWG-to-Excel script. The long-term target is:

```text
DWG/CAD source
  -> parser output
  -> normalized engineering objects
  -> Object Store
  -> spatial/rule/LLM candidate inference
  -> accepted Engineering Graph
  -> BOM, installation table, axis table, IO Mapping, schedules
```

## Core Architecture Principles

- Use `Object + Relation + Context` as the stable core model.
- Keep `geometry`, `cad_meta`, and `attribute` separate from `cad_object`.
- Use EAV-style `attribute` rows for object-specific fields instead of adding fixed columns for every device type.
- Rules, parsers, and LLMs must write suggestions to `relation_candidate` first.
- The final `relation` table stores accepted engineering relations only.
- Human corrections must be traceable through `manual_relation` and/or `correction_log`.
- Keep SQLite suitable for prototype/local validation while preserving a path to PostgreSQL/PostGIS.
- LLMs must consume structured JSON/object data, not raw DWG files.

## Non-Negotiable Boundaries

Do not change these without an explicit architecture task:

- `dwg_rec_system/schema.sql`
- `dwg_rec_system/models.py`
- relation flow: `relation_candidate -> relation`
- object identity rule: `source_file + handle`
- core repository semantics in `dwg_rec_system/repositories.py`
- migration direction described in `migrations/`

Do not bypass `ObjectStore` when importing recognized CAD objects unless the task explicitly asks for a low-level repository change.

Do not let an LLM, parser, or rule engine write directly to final `relation` as a first step. Use `relation_candidate`, then accept or reject.

Do not introduce external runtime dependencies unless the assigned task explicitly allows them.

Do not perform broad refactors, formatting churn, or unrelated cleanup in task branches.

## Current Priority

The next major milestone is:

```text
external CAD parser output
  -> normalized JSON
  -> ObjectInput
  -> ObjectStore
  -> spatial query / relation inference / CSV export
```

Before connecting a real DWG parser, define and implement a stable normalized JSON import path.

## Repository Map

```text
dwg_rec_system/
  db.py                 database connection, initialization, compatibility migrations
  schema.sql            SQLite schema and prototype database contract
  models.py             input dataclasses for objects, geometry, CAD metadata, rules
  repositories.py       low-level data access and relation/correction repositories
  cli.py                command-line entry point
  services/
    object_store.py     object ingestion service
    spatial_index.py    nearest, contains_point, overlap queries
    relation_engine.py  rule-based relation inference
    exports.py          CSV export
  taxonomy/
    cad_object_taxonomy.json
    engineering_class_profiles.json

migrations/
  sqlite/               SQLite notes
  postgres/             PostgreSQL/PostGIS target notes

tests/
  test_database_flow.py baseline object/spatial/relation test
```

## Agent Working Rules

Each sub-agent must receive one bounded task package. A task package must specify:

- Objective
- Allowed files or directories
- Disallowed changes
- Required implementation behavior
- Required tests
- Required validation commands

Sub-agents should:

- Read this file before editing.
- Read `docs/architecture.md` before touching application code.
- Stay within the assigned file scope.
- Add or update tests for behavioral changes.
- Run `python -m pytest -q` before reporting completion.
- Report any schema or architecture conflict instead of silently changing core design.

## First-Round Task Order

Use `docs/agent_tasks_round_1.md` for the first implementation round.

Recommended execution:

1. Agent A: normalized JSON importer.
2. Agent B: taxonomy seeder.
3. Agent C: import and taxonomy tests.
4. Agent D: README/docs/sample updates.

Agents A and B can work in parallel if they avoid editing the same sections of `cli.py`. If there is a conflict, finish Agent A first because the import path is the main milestone.

## Validation Baseline

Run this before and after meaningful changes:

```powershell
python -m pytest -q
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-demo
python -m dwg_rec_system.cli infer-relations
python -m dwg_rec_system.cli export-csv
```

When the normalized JSON importer exists, also run:

```powershell
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json
python -m dwg_rec_system.cli list-objects
```

## Review Standard

A completed task is acceptable only when:

- It preserves the architecture boundaries above.
- It has focused tests or a clear reason tests are not applicable.
- It does not introduce unrelated changes.
- It keeps commands working on a clean local checkout.
- It documents any new CLI command, input format, or operational assumption.
