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


def add_columns(connection: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, definition in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
