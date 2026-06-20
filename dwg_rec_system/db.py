from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DB_PATH = Path("data/dwg_rec_system.db")


def database_path() -> Path:
    return Path(os.environ.get("DWG_REC_DB", DEFAULT_DB_PATH))


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path else database_path()
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def session(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    connection = connect(path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_database(path: str | Path | None = None) -> Path:
    db_path = Path(path) if path else database_path()
    schema_path = Path(__file__).with_name("schema.sql")
    with session(db_path) as connection:
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        apply_compat_migrations(connection)
    return db_path


def apply_compat_migrations(connection: sqlite3.Connection) -> None:
    """Add columns needed by the evolving schema on existing SQLite databases."""
    create_compat_tables(connection)
    add_columns(
        connection,
        "drawing",
        {
            "project_id": "TEXT REFERENCES project(id) ON DELETE SET NULL",
        },
    )
    add_columns(
        connection,
        "import_job",
        {
            "project_id": "TEXT REFERENCES project(id) ON DELETE SET NULL",
            "parser_version": "TEXT",
        },
    )
    add_columns(
        connection,
        "cad_object",
        {
            "import_job_id": "TEXT REFERENCES import_job(id) ON DELETE SET NULL",
            "class_id": "TEXT REFERENCES object_class(id) ON DELETE SET NULL",
            "parser_name": "TEXT",
            "parser_version": "TEXT",
            "recognition_model": "TEXT",
            "recognition_version": "TEXT",
        },
    )
    add_columns(
        connection,
        "geometry",
        {
            "geometry_type": "TEXT NOT NULL DEFAULT 'bbox'",
            "geometry_wkt": "TEXT",
            "geometry_srid": "INTEGER NOT NULL DEFAULT 0",
        },
    )
    add_columns(
        connection,
        "attribute",
        {
            "normalized_value": "TEXT",
            "unit": "TEXT",
            "namespace": "TEXT NOT NULL DEFAULT 'default'",
            "is_inferred": "INTEGER NOT NULL DEFAULT 0",
        },
    )
    add_columns(
        connection,
        "relation",
        {
            "candidate_id": "TEXT REFERENCES relation_candidate(id) ON DELETE SET NULL",
        },
    )
    add_columns(
        connection,
        "rule_template",
        {
            "version": "TEXT NOT NULL DEFAULT '1'",
            "rule_kind": "TEXT NOT NULL DEFAULT 'spatial'",
            "expression": "TEXT",
            "valid_from": "TEXT",
            "valid_to": "TEXT",
        },
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_attribute_namespace_key ON attribute(namespace, key)"
    )


def create_compat_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS quantity_item (
            id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES project(id) ON DELETE SET NULL,
            drawing_id TEXT REFERENCES drawing(id) ON DELETE SET NULL,
            source_object_id TEXT REFERENCES cad_object(id) ON DELETE SET NULL,
            class_code TEXT NOT NULL,
            discipline TEXT,
            item_name TEXT NOT NULL,
            spec TEXT,
            unit TEXT NOT NULL,
            quantity REAL NOT NULL CHECK (quantity >= 0),
            quantity_method TEXT NOT NULL CHECK (
                quantity_method IN (
                    'count_by_object',
                    'length_by_geometry',
                    'area_by_geometry',
                    'grouped_count',
                    'formula',
                    'manual_review'
                )
            ),
            group_key TEXT,
            location TEXT,
            system_code TEXT,
            confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
            source TEXT NOT NULL DEFAULT 'auto' CHECK (
                source IN ('auto', 'manual', 'rule', 'import', 'parser', 'llm')
            ),
            evidence_json TEXT,
            status TEXT NOT NULL DEFAULT 'auto' CHECK (
                status IN ('auto', 'reviewed', 'corrected', 'rejected')
            ),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_quantity_item_project ON quantity_item(project_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_quantity_item_drawing ON quantity_item(drawing_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_quantity_item_source_object ON quantity_item(source_object_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_quantity_item_class ON quantity_item(class_code)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_quantity_item_status ON quantity_item(status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_quantity_item_group ON quantity_item(group_key)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cost_item (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            discipline TEXT,
            class_code TEXT NOT NULL,
            spec_pattern TEXT,
            unit TEXT NOT NULL,
            unit_price_material REAL NOT NULL DEFAULT 0 CHECK (unit_price_material >= 0),
            unit_price_labor REAL NOT NULL DEFAULT 0 CHECK (unit_price_labor >= 0),
            unit_price_machine REAL NOT NULL DEFAULT 0 CHECK (unit_price_machine >= 0),
            currency TEXT NOT NULL DEFAULT 'CNY',
            region TEXT,
            version TEXT,
            effective_from TEXT,
            effective_to TEXT,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_cost_item_class_unit ON cost_item(class_code, unit)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_cost_item_status ON cost_item(status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_cost_item_discipline ON cost_item(discipline)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS budget_item (
            id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES project(id) ON DELETE SET NULL,
            drawing_id TEXT REFERENCES drawing(id) ON DELETE SET NULL,
            quantity_item_id TEXT REFERENCES quantity_item(id) ON DELETE SET NULL,
            cost_item_id TEXT REFERENCES cost_item(id) ON DELETE SET NULL,
            class_code TEXT,
            discipline TEXT,
            item_name TEXT NOT NULL,
            spec TEXT,
            unit TEXT NOT NULL,
            quantity REAL NOT NULL CHECK (quantity >= 0),
            unit_price_material REAL NOT NULL DEFAULT 0 CHECK (unit_price_material >= 0),
            unit_price_labor REAL NOT NULL DEFAULT 0 CHECK (unit_price_labor >= 0),
            unit_price_machine REAL NOT NULL DEFAULT 0 CHECK (unit_price_machine >= 0),
            material_cost REAL NOT NULL DEFAULT 0 CHECK (material_cost >= 0),
            labor_cost REAL NOT NULL DEFAULT 0 CHECK (labor_cost >= 0),
            machine_cost REAL NOT NULL DEFAULT 0 CHECK (machine_cost >= 0),
            total_cost REAL NOT NULL DEFAULT 0 CHECK (total_cost >= 0),
            pricing_source TEXT NOT NULL DEFAULT 'auto',
            confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
            evidence_json TEXT,
            status TEXT NOT NULL DEFAULT 'auto' CHECK (
                status IN ('auto', 'review', 'matched', 'unmatched', 'corrected', 'rejected')
            ),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_budget_item_project ON budget_item(project_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_budget_item_drawing ON budget_item(drawing_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_budget_item_quantity ON budget_item(quantity_item_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_budget_item_cost ON budget_item(cost_item_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_budget_item_class ON budget_item(class_code)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_budget_item_status ON budget_item(status)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS install_task (
            id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES project(id) ON DELETE SET NULL,
            drawing_id TEXT REFERENCES drawing(id) ON DELETE SET NULL,
            object_id TEXT REFERENCES cad_object(id) ON DELETE SET NULL,
            class_code TEXT NOT NULL,
            discipline TEXT,
            task_name TEXT NOT NULL,
            work_package TEXT,
            location TEXT,
            system_code TEXT,
            priority INTEGER NOT NULL DEFAULT 100,
            estimated_duration REAL,
            crew_type TEXT,
            source TEXT NOT NULL DEFAULT 'auto' CHECK (
                source IN ('auto', 'manual', 'rule', 'import', 'parser', 'llm')
            ),
            confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
            evidence_json TEXT,
            status TEXT NOT NULL DEFAULT 'auto' CHECK (
                status IN ('auto', 'review', 'ready', 'blocked', 'corrected', 'rejected', 'done')
            ),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_install_task_project ON install_task(project_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_install_task_drawing ON install_task(drawing_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_install_task_object ON install_task(object_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_install_task_class ON install_task(class_code)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_install_task_status ON install_task(status)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS install_dependency (
            id TEXT PRIMARY KEY,
            predecessor_task_id TEXT NOT NULL REFERENCES install_task(id) ON DELETE CASCADE,
            successor_task_id TEXT NOT NULL REFERENCES install_task(id) ON DELETE CASCADE,
            dependency_type TEXT NOT NULL CHECK (
                dependency_type IN (
                    'finish_to_start',
                    'start_to_start',
                    'inspection_before',
                    'pressure_test_before',
                    'power_before_commissioning',
                    'profile_prerequisite'
                )
            ),
            reason TEXT,
            source TEXT NOT NULL DEFAULT 'auto' CHECK (
                source IN ('auto', 'manual', 'rule', 'import', 'parser', 'llm')
            ),
            confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
            evidence_json TEXT,
            status TEXT NOT NULL DEFAULT 'auto' CHECK (
                status IN ('auto', 'review', 'corrected', 'rejected')
            ),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_install_dependency_predecessor
        ON install_dependency(predecessor_task_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_install_dependency_successor
        ON install_dependency(successor_task_id)
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_install_dependency_status ON install_dependency(status)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS install_instruction (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES install_task(id) ON DELETE CASCADE,
            instruction_text TEXT NOT NULL,
            generator TEXT NOT NULL DEFAULT 'template',
            generator_version TEXT NOT NULL DEFAULT '0.1',
            source_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_install_instruction_task
        ON install_instruction(task_id)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_plan (
            id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES project(id) ON DELETE SET NULL,
            drawing_id TEXT REFERENCES drawing(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            scope_json TEXT,
            generator TEXT NOT NULL DEFAULT 'workflow_plan_generator',
            generator_version TEXT NOT NULL DEFAULT '0.1',
            status TEXT NOT NULL DEFAULT 'review' CHECK (
                status IN ('draft', 'review', 'ready', 'superseded', 'rejected')
            ),
            summary_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_plan_project ON workflow_plan(project_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_plan_drawing ON workflow_plan(drawing_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_plan_status ON workflow_plan(status)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_step (
            id TEXT PRIMARY KEY,
            plan_id TEXT NOT NULL REFERENCES workflow_plan(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES install_task(id) ON DELETE CASCADE,
            sequence_no INTEGER NOT NULL,
            sequence_group TEXT,
            discipline TEXT,
            work_package TEXT,
            location TEXT,
            system_code TEXT,
            dependency_count INTEGER NOT NULL DEFAULT 0,
            blocked_by_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'planned' CHECK (
                status IN ('planned', 'review', 'blocked', 'unplanned', 'done', 'rejected')
            ),
            evidence_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (plan_id, task_id)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_step_plan ON workflow_step(plan_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_step_task ON workflow_step(task_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_step_status ON workflow_step(status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_step_sequence ON workflow_step(plan_id, sequence_no)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_issue (
            id TEXT PRIMARY KEY,
            plan_id TEXT NOT NULL REFERENCES workflow_plan(id) ON DELETE CASCADE,
            task_id TEXT REFERENCES install_task(id) ON DELETE SET NULL,
            dependency_id TEXT REFERENCES install_dependency(id) ON DELETE SET NULL,
            severity TEXT NOT NULL CHECK (severity IN ('error', 'warning', 'info')),
            category TEXT NOT NULL CHECK (
                category IN (
                    'cycle',
                    'missing_dependency_task',
                    'review_dependency',
                    'blocked_predecessor',
                    'unplanned_task',
                    'task_needs_review',
                    'missing_scope'
                )
            ),
            code TEXT NOT NULL,
            message TEXT NOT NULL,
            evidence_json TEXT,
            status TEXT NOT NULL DEFAULT 'open' CHECK (
                status IN ('open', 'accepted', 'resolved', 'rejected')
            ),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_issue_plan ON workflow_issue(plan_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_issue_task ON workflow_issue(task_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_issue_dependency ON workflow_issue(dependency_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_issue_severity ON workflow_issue(severity)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_issue_category ON workflow_issue(category)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_issue_status ON workflow_issue(status)"
    )
    create_recognition_compat_tables(connection)


def create_recognition_compat_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS source_document (
            id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES project(id) ON DELETE SET NULL,
            source_uri TEXT NOT NULL UNIQUE,
            source_type TEXT NOT NULL DEFAULT 'unknown' CHECK (
                source_type IN ('pdf', 'dwg', 'dxf', 'image', 'cad_export', 'json', 'unknown')
            ),
            file_hash TEXT,
            title TEXT,
            parser_name TEXT,
            parser_version TEXT,
            metadata_json TEXT,
            status TEXT NOT NULL DEFAULT 'active' CHECK (
                status IN ('active', 'archived', 'failed')
            ),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_document_project ON source_document(project_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_document_status ON source_document(status)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS drawing_page (
            id TEXT PRIMARY KEY,
            source_document_id TEXT NOT NULL REFERENCES source_document(id) ON DELETE CASCADE,
            drawing_id TEXT REFERENCES drawing(id) ON DELETE SET NULL,
            page_no INTEGER,
            layout_name TEXT,
            width REAL,
            height REAL,
            unit TEXT,
            scale TEXT,
            rotation REAL NOT NULL DEFAULT 0,
            metadata_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (source_document_id, page_no, layout_name)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_drawing_page_source ON drawing_page(source_document_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_drawing_page_drawing ON drawing_page(drawing_id)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS drawing_primitive (
            id TEXT PRIMARY KEY,
            page_id TEXT NOT NULL REFERENCES drawing_page(id) ON DELETE CASCADE,
            source_local_id TEXT NOT NULL,
            primitive_type TEXT NOT NULL DEFAULT 'unknown' CHECK (
                primitive_type IN (
                    'line',
                    'polyline',
                    'path',
                    'rect',
                    'circle',
                    'arc',
                    'text',
                    'image',
                    'block',
                    'symbol',
                    'unknown'
                )
            ),
            geometry_json TEXT,
            bbox_json TEXT,
            text TEXT,
            style_json TEXT,
            raw_json TEXT,
            confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (page_id, source_local_id)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_drawing_primitive_page ON drawing_primitive(page_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_drawing_primitive_type ON drawing_primitive(primitive_type)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS recognition_candidate (
            id TEXT PRIMARY KEY,
            page_id TEXT NOT NULL REFERENCES drawing_page(id) ON DELETE CASCADE,
            source_local_id TEXT NOT NULL,
            candidate_type TEXT NOT NULL DEFAULT 'unknown' CHECK (
                candidate_type IN ('object', 'text_label', 'attribute', 'relation_hint', 'geometry_group', 'unknown')
            ),
            class_code TEXT,
            label TEXT,
            confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
            source TEXT NOT NULL CHECK (
                source IN ('rule', 'parser', 'ocr', 'cv', 'llm', 'manual', 'import')
            ),
            model_name TEXT,
            model_version TEXT,
            geometry_json TEXT,
            bbox_json TEXT,
            attributes_json TEXT,
            evidence_json TEXT,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (
                status IN ('pending', 'accepted', 'rejected', 'superseded', 'merged')
            ),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (page_id, source_local_id)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_recognition_candidate_page ON recognition_candidate(page_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_recognition_candidate_class ON recognition_candidate(class_code)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_recognition_candidate_status ON recognition_candidate(status)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS recognition_candidate_primitive (
            id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL REFERENCES recognition_candidate(id) ON DELETE CASCADE,
            primitive_id TEXT NOT NULL REFERENCES drawing_primitive(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'context' CHECK (
                role IN ('geometry', 'text', 'symbol', 'anchor', 'context', 'negative')
            ),
            weight REAL NOT NULL DEFAULT 1.0,
            evidence_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (candidate_id, primitive_id, role)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_candidate_primitive_candidate
        ON recognition_candidate_primitive(candidate_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_candidate_primitive_primitive
        ON recognition_candidate_primitive(primitive_id)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS object_hypothesis (
            id TEXT PRIMARY KEY,
            page_id TEXT NOT NULL REFERENCES drawing_page(id) ON DELETE CASCADE,
            source_document_id TEXT NOT NULL REFERENCES source_document(id) ON DELETE CASCADE,
            class_code TEXT NOT NULL,
            subtype TEXT,
            source_local_id TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
            geometry_json TEXT,
            bbox_json TEXT,
            attributes_json TEXT,
            evidence_json TEXT,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (
                status IN ('pending', 'accepted', 'rejected', 'merged', 'superseded')
            ),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (page_id, source_local_id)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_object_hypothesis_page ON object_hypothesis(page_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_object_hypothesis_source ON object_hypothesis(source_document_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_object_hypothesis_class ON object_hypothesis(class_code)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_object_hypothesis_status ON object_hypothesis(status)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS hypothesis_candidate (
            id TEXT PRIMARY KEY,
            hypothesis_id TEXT NOT NULL REFERENCES object_hypothesis(id) ON DELETE CASCADE,
            candidate_id TEXT NOT NULL REFERENCES recognition_candidate(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'primary' CHECK (
                role IN ('primary', 'attribute', 'label', 'geometry', 'context', 'negative')
            ),
            weight REAL NOT NULL DEFAULT 1.0,
            evidence_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (hypothesis_id, candidate_id, role)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hypothesis_candidate_hypothesis
        ON hypothesis_candidate(hypothesis_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hypothesis_candidate_candidate
        ON hypothesis_candidate(candidate_id)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS hypothesis_to_object (
            id TEXT PRIMARY KEY,
            hypothesis_id TEXT NOT NULL UNIQUE REFERENCES object_hypothesis(id) ON DELETE CASCADE,
            object_id TEXT NOT NULL REFERENCES cad_object(id) ON DELETE CASCADE,
            accepted_by TEXT,
            acceptance_method TEXT NOT NULL DEFAULT 'manual' CHECK (
                acceptance_method IN ('manual', 'rule', 'threshold', 'import')
            ),
            evidence_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hypothesis_to_object_object
        ON hypothesis_to_object(object_id)
        """
    )


def add_columns(connection: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, definition in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
