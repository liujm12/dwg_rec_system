import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from dwg_rec_system.db import init_database, session
from dwg_rec_system.importers.normalized_json import NormalizedJsonImporter
from dwg_rec_system.repositories import (
    InstallDependencyRepository,
    InstallInstructionRepository,
    InstallTaskRepository,
    RelationCandidateRepository,
    RelationRepository,
)
from dwg_rec_system.services.exports import CsvExporter
from dwg_rec_system.services.installation import (
    InstallDependencyGenerator,
    InstallInstructionGenerator,
    InstallTaskGenerator,
)
from dwg_rec_system.services.relation_engine import RelationEngine
from dwg_rec_system.services.rules import RuleTemplateSeeder
from dwg_rec_system.services.taxonomy import TaxonomySeeder


def _profile_path(tmp_path: Path, profiles: list[dict]) -> Path:
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"class_profiles": profiles}, ensure_ascii=False), encoding="utf-8")
    return path


def _profile(code: str, work_package: str = "test installation") -> dict:
    return {
        "code": code,
        "profile_group": "TEST",
        "expected_attributes": ["tag", "location", "system"],
        "relations": ["mounted_on", "powered_by", "connected_to"],
        "installation": {
            "work_package": work_package,
            "default_steps": ["verify tag", "set equipment", "test installation"],
            "required_predecessors": ["ROOM_READY"],
        },
    }


def _import_payload(connection, objects: list[dict]) -> dict:
    return NormalizedJsonImporter(connection).import_data(
        {
            "project": {"code": "INST", "name": "Installation Test"},
            "drawing": {"drawing_no": "I-001", "source_file": "install.dwg"},
            "objects": objects,
        }
    )


def _object_by_handle(connection, handle: str) -> str:
    row = connection.execute("SELECT id FROM cad_object WHERE handle = ?", (handle,)).fetchone()
    assert row
    return row["id"]


def test_install_tables_exist_with_expected_columns(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        task_columns = {row["name"] for row in connection.execute("PRAGMA table_info(install_task)").fetchall()}
        dependency_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(install_dependency)").fetchall()
        }
        instruction_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(install_instruction)").fetchall()
        }

    assert {"id", "object_id", "class_code", "work_package", "status", "evidence_json"} <= task_columns
    assert {"id", "predecessor_task_id", "successor_task_id", "dependency_type"} <= dependency_columns
    assert {"id", "task_id", "instruction_text", "generator", "source_json"} <= instruction_columns


def test_install_repositories_create_list_and_preserve_reviewed_rows(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        tasks = InstallTaskRepository(connection)
        auto_id = tasks.create(class_code="DDC", task_name="Install DDC", status="auto")
        corrected_id = tasks.create(class_code="DDC", task_name="Corrected DDC", status="corrected")
        dependency_id = InstallDependencyRepository(connection).create(
            predecessor_task_id=corrected_id,
            successor_task_id=auto_id,
            dependency_type="finish_to_start",
            status="review",
            evidence={"source": "test"},
        )
        instruction_id = InstallInstructionRepository(connection).create(
            task_id=corrected_id,
            instruction_text="Install corrected task",
            source={"source": "test"},
        )

        assert {row["id"] for row in tasks.list(class_code="DDC")} == {auto_id, corrected_id}
        assert InstallDependencyRepository(connection).list(status="review")[0]["id"] == dependency_id
        assert InstallInstructionRepository(connection).list(task_id=corrected_id)[0]["id"] == instruction_id

        cleared = tasks.clear_auto()
        rows = tasks.list()

    assert cleared == 1
    assert [row["id"] for row in rows] == [corrected_id]


def test_install_task_generation_uses_profile_attributes_and_evidence(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(tmp_path, [_profile("CONTROL_PANEL", "control panel installation")])
    init_database(db_path)

    with session(db_path) as connection:
        _import_payload(
            connection,
            [
                {
                    "class_name": "CONTROL_PANEL",
                    "source_file": "install.dwg",
                    "handle": "CP-01",
                    "confidence": 0.95,
                    "attributes": {"tag": "CP-01", "location": "Room 101", "system": "BMS"},
                }
            ],
        )
        summary = InstallTaskGenerator(connection, profile).generate_tasks()
        row = InstallTaskRepository(connection).list()[0]
        evidence = json.loads(row["evidence_json"])

    assert summary["created"] == 1
    assert row["task_name"] == "Install CONTROL_PANEL CP-01"
    assert row["work_package"] == "control panel installation"
    assert row["location"] == "Room 101"
    assert row["system_code"] == "BMS"
    assert evidence["installation"]["default_steps"] == ["verify tag", "set equipment", "test installation"]


def test_install_task_generation_review_skip_filters_and_idempotency(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(tmp_path, [_profile("DDC")])
    init_database(db_path)

    with session(db_path) as connection:
        result = _import_payload(
            connection,
            [
                {"class_name": "DDC", "source_file": "install.dwg", "handle": "D-01", "confidence": 0.5},
                {"class_name": "UNKNOWN", "source_file": "install.dwg", "handle": "U-01"},
            ],
        )
        drawing_id = result["drawing_id"]
        first = InstallTaskGenerator(connection, profile).generate_tasks(drawing_id=drawing_id)
        second = InstallTaskGenerator(connection, profile).generate_tasks(drawing_id=drawing_id)
        rows = InstallTaskRepository(connection).list(status="review")

    assert first["review"] == 1
    assert first["skipped_no_profile"] == 1
    assert second["cleared"] == 1
    assert len(rows) == 1
    assert rows[0]["drawing_id"] == drawing_id


def test_mounted_on_and_powered_by_create_target_before_source_dependencies(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(tmp_path, [_profile("DDC"), _profile("CONTROL_PANEL")])
    init_database(db_path)

    with session(db_path) as connection:
        _import_payload(
            connection,
            [
                {"class_name": "DDC", "source_file": "install.dwg", "handle": "D-01"},
                {"class_name": "CONTROL_PANEL", "source_file": "install.dwg", "handle": "CP-01"},
            ],
        )
        ddc_id = _object_by_handle(connection, "D-01")
        panel_id = _object_by_handle(connection, "CP-01")
        RelationRepository(connection).upsert(ddc_id, panel_id, "mounted_on", 0.9, source="rule")
        RelationRepository(connection).upsert(ddc_id, panel_id, "powered_by", 0.8, source="rule")
        InstallTaskGenerator(connection, profile).generate_tasks()
        summary = InstallDependencyGenerator(connection).generate_dependencies()
        rows = InstallDependencyRepository(connection).list()
        tasks = {task["id"]: task for task in InstallTaskRepository(connection).list()}

    assert summary["created"] == 2
    assert {row["dependency_type"] for row in rows} == {"finish_to_start", "power_before_commissioning"}
    for row in rows:
        assert tasks[row["predecessor_task_id"]]["class_code"] == "CONTROL_PANEL"
        assert tasks[row["successor_task_id"]]["class_code"] == "DDC"


def test_connected_to_creates_review_dependency_and_candidates_are_ignored(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(tmp_path, [_profile("DDC"), _profile("CONTROL_PANEL")])
    init_database(db_path)

    with session(db_path) as connection:
        _import_payload(
            connection,
            [
                {"class_name": "DDC", "source_file": "install.dwg", "handle": "D-01"},
                {"class_name": "CONTROL_PANEL", "source_file": "install.dwg", "handle": "CP-01"},
            ],
        )
        ddc_id = _object_by_handle(connection, "D-01")
        panel_id = _object_by_handle(connection, "CP-01")
        RelationCandidateRepository(connection).upsert(ddc_id, panel_id, "powered_by", 0.9, "rule")
        RelationRepository(connection).upsert(ddc_id, panel_id, "connected_to", 0.9, source="rule")
        InstallTaskGenerator(connection, profile).generate_tasks()
        first = InstallDependencyGenerator(connection).generate_dependencies()
        second = InstallDependencyGenerator(connection).generate_dependencies()
        rows = InstallDependencyRepository(connection).list()

    assert first["created"] == 1
    assert second["cleared"] == 1
    assert len(rows) == 1
    assert rows[0]["dependency_type"] == "start_to_start"
    assert rows[0]["status"] == "review"


def test_dependency_generation_skips_missing_task(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(tmp_path, [_profile("DDC")])
    init_database(db_path)

    with session(db_path) as connection:
        _import_payload(
            connection,
            [
                {"class_name": "DDC", "source_file": "install.dwg", "handle": "D-01"},
                {"class_name": "UNKNOWN_PANEL", "source_file": "install.dwg", "handle": "P-01"},
            ],
        )
        ddc_id = _object_by_handle(connection, "D-01")
        panel_id = _object_by_handle(connection, "P-01")
        RelationRepository(connection).upsert(ddc_id, panel_id, "mounted_on", 0.9, source="rule")
        InstallTaskGenerator(connection, profile).generate_tasks()
        summary = InstallDependencyGenerator(connection).generate_dependencies()
        rows = InstallDependencyRepository(connection).list()

    assert summary["skipped_missing_task"] == 1
    assert rows == []


def test_instruction_generation_includes_steps_dependencies_and_review_note(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(tmp_path, [_profile("DDC"), _profile("CONTROL_PANEL")])
    init_database(db_path)

    with session(db_path) as connection:
        _import_payload(
            connection,
            [
                {"class_name": "DDC", "source_file": "install.dwg", "handle": "D-01", "confidence": 0.5},
                {"class_name": "CONTROL_PANEL", "source_file": "install.dwg", "handle": "CP-01"},
            ],
        )
        ddc_id = _object_by_handle(connection, "D-01")
        panel_id = _object_by_handle(connection, "CP-01")
        RelationRepository(connection).upsert(ddc_id, panel_id, "mounted_on", 0.9, source="rule")
        InstallTaskGenerator(connection, profile).generate_tasks()
        InstallDependencyGenerator(connection).generate_dependencies()
        first = InstallInstructionGenerator(connection).generate_instructions()
        second = InstallInstructionGenerator(connection).generate_instructions()
        rows = InstallInstructionRepository(connection).list()

    assert first["created"] == 2
    assert second["cleared"] == 2
    text = "\n".join(row["instruction_text"] for row in rows)
    assert "Work package: test installation" in text
    assert "1. verify tag" in text
    assert "Dependencies:" in text
    assert "Review note:" in text


def test_install_task_csv_export_writes_expected_headers(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        InstallTaskRepository(connection).create(
            class_code="DDC",
            task_name="Install DDC",
            work_package="control equipment installation",
        )
        output = CsvExporter(connection).export_install_tasks(tmp_path / "install_tasks.csv")

    with output.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        assert {
            "object_id",
            "class_code",
            "discipline",
            "task_name",
            "work_package",
            "location",
            "system_code",
            "priority",
            "status",
            "confidence",
        } <= set(reader.fieldnames or [])


def test_cli_installation_flow_after_sample_import(tmp_path):
    db_path = tmp_path / "cli.db"
    output_path = tmp_path / "install_tasks.csv"
    env = os.environ.copy()
    env["DWG_REC_DB"] = str(db_path)
    cwd = Path(__file__).resolve().parents[1]

    commands = [
        ["init-db"],
        ["seed-taxonomy"],
        ["import-json", "--input", "samples/demo_parsed.json", "--strict-taxonomy"],
        ["seed-rules", "--input", "samples/demo_rules.json"],
        ["infer-relations"],
        ["generate-install-tasks"],
        ["generate-install-dependencies"],
        ["generate-install-instructions"],
    ]
    for command in commands:
        result = subprocess.run(
            [sys.executable, "-m", "dwg_rec_system.cli", *command],
            cwd=cwd,
            env=env,
            check=True,
            text=True,
            capture_output=True,
        )
    assert json.loads(result.stdout)["created"] >= 2

    tasks_result = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-install-tasks"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    tasks = json.loads(tasks_result.stdout)
    assert {row["class_code"] for row in tasks} >= {"CONTROL_PANEL", "DDC"}

    filtered_result = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-install-tasks", "--class-code", "DDC"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert {row["class_code"] for row in json.loads(filtered_result.stdout)} == {"DDC"}

    deps_result = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-install-dependencies"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert len(json.loads(deps_result.stdout)) >= 1

    instructions_result = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-install-instructions"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert len(json.loads(instructions_result.stdout)) == len(tasks)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "dwg_rec_system.cli",
            "export-install-tasks-csv",
            "--output",
            str(output_path),
        ],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert output_path.exists()
