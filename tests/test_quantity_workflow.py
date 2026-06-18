import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from dwg_rec_system.db import init_database, session
from dwg_rec_system.importers.normalized_json import NormalizedJsonImporter
from dwg_rec_system.repositories import QuantityRepository
from dwg_rec_system.services.exports import CsvExporter
from dwg_rec_system.services.quantity import QuantityGenerator
from dwg_rec_system.services.taxonomy import TaxonomySeeder


def _profile_path(tmp_path: Path, profiles: list[dict]) -> Path:
    path = tmp_path / "profiles.json"
    path.write_text(
        json.dumps({"class_profiles": profiles}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _import_payload(connection, objects: list[dict]):
    return NormalizedJsonImporter(connection).import_data(
        {
            "project": {"code": "QTY", "name": "Quantity Test"},
            "drawing": {"drawing_no": "Q-001", "source_file": "qty.dwg"},
            "objects": objects,
        }
    )


def test_quantity_repository_create_list_and_preserve_non_auto(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        repo = QuantityRepository(connection)
        auto_id = repo.upsert(
            class_code="VALVE",
            item_name="VALVE",
            unit="pcs",
            quantity=1,
            quantity_method="count_by_object",
        )
        manual_id = repo.upsert(
            class_code="VALVE",
            item_name="VALVE",
            unit="pcs",
            quantity=2,
            quantity_method="count_by_object",
            source="manual",
            status="reviewed",
        )

        rows = repo.list(class_code="VALVE")
        assert {row["id"] for row in rows} == {auto_id, manual_id}

        cleared = repo.clear_auto()
        rows_after = repo.list()

    assert cleared == 1
    assert [row["id"] for row in rows_after] == [manual_id]


def test_count_by_object_creates_quantity_rows(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        TaxonomySeeder(connection).seed_file()
        _import_payload(
            connection,
            [
                {
                    "class_name": "CONTROL_PANEL",
                    "source_file": "qty.dwg",
                    "handle": "CP-01",
                    "attributes": {"tag": "CP-01", "voltage": "220V"},
                }
            ],
        )
        summary = QuantityGenerator(connection).generate()
        rows = QuantityRepository(connection).list(class_code="CONTROL_PANEL")

    assert summary["created"] == 1
    assert rows[0]["quantity"] == 1
    assert rows[0]["unit"] == "set"
    assert rows[0]["quantity_method"] == "count_by_object"


def test_grouped_count_uses_profile_group_by(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(
        tmp_path,
        [
            {
                "code": "VALVE",
                "profile_group": "PIPING",
                "expected_attributes": ["diameter", "material"],
                "budget": {
                    "unit": "pcs",
                    "quantity_method": "grouped_count",
                    "group_by": ["diameter", "material"],
                },
            }
        ],
    )
    init_database(db_path)

    with session(db_path) as connection:
        _import_payload(
            connection,
            [
                {
                    "class_name": "VALVE",
                    "source_file": "qty.dwg",
                    "handle": "V-01",
                    "attributes": {"diameter": "DN100", "material": "stainless"},
                },
                {
                    "class_name": "VALVE",
                    "source_file": "qty.dwg",
                    "handle": "V-02",
                    "attributes": {"diameter": "DN100", "material": "stainless"},
                },
            ],
        )
        summary = QuantityGenerator(connection, profile).generate()
        rows = QuantityRepository(connection).list(class_code="VALVE")

    assert summary["created"] == 1
    assert rows[0]["quantity"] == 2
    assert rows[0]["quantity_method"] == "grouped_count"
    assert rows[0]["group_key"] == "VALVE|diameter=DN100|material=stainless"


def test_length_by_geometry_uses_raw_length_or_width(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(
        tmp_path,
        [
            {
                "code": "PIPE",
                "profile_group": "PIPING",
                "expected_attributes": ["diameter"],
                "budget": {
                    "unit": "m",
                    "quantity_method": "length_by_geometry",
                    "group_by": ["diameter"],
                },
            }
        ],
    )
    init_database(db_path)

    with session(db_path) as connection:
        _import_payload(
            connection,
            [
                {
                    "class_name": "PIPE",
                    "source_file": "qty.dwg",
                    "handle": "P-01",
                    "geometry": {"width": 12},
                    "attributes": {"diameter": "DN50"},
                },
                {
                    "class_name": "PIPE",
                    "source_file": "qty.dwg",
                    "handle": "P-02",
                    "geometry": {"width": 1, "raw_geometry": {"length": 25}},
                    "attributes": {"diameter": "DN80"},
                },
            ],
        )
        QuantityGenerator(connection, profile).generate()
        rows = QuantityRepository(connection).list(class_code="PIPE")

    quantities = sorted(row["quantity"] for row in rows)
    assert quantities == [12, 25]


def test_area_by_geometry_uses_width_height_or_manual_review(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(
        tmp_path,
        [
            {
                "code": "DUCT",
                "profile_group": "HVAC",
                "expected_attributes": ["material"],
                "budget": {
                    "unit": "m2",
                    "quantity_method": "area_by_geometry",
                    "group_by": ["material"],
                },
            }
        ],
    )
    init_database(db_path)

    with session(db_path) as connection:
        _import_payload(
            connection,
            [
                {
                    "class_name": "DUCT",
                    "source_file": "qty.dwg",
                    "handle": "D-01",
                    "geometry": {"width": 10, "height": 5},
                    "attributes": {"material": "galvanized"},
                },
                {
                    "class_name": "DUCT",
                    "source_file": "qty.dwg",
                    "handle": "D-02",
                    "attributes": {"material": "galvanized"},
                },
            ],
        )
        summary = QuantityGenerator(connection, profile).generate()
        rows = QuantityRepository(connection).list(class_code="DUCT")

    assert summary["manual_review"] == 1
    assert {row["quantity_method"] for row in rows} == {"area_by_geometry", "manual_review"}
    assert sorted(row["quantity"] for row in rows) == [0, 50]


def test_objects_without_profiles_are_skipped(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(tmp_path, [])
    init_database(db_path)

    with session(db_path) as connection:
        _import_payload(
            connection,
            [
                {
                    "class_name": "UNKNOWN_DEVICE",
                    "source_file": "qty.dwg",
                    "handle": "U-01",
                }
            ],
        )
        summary = QuantityGenerator(connection, profile).generate()
        rows = QuantityRepository(connection).list()

    assert summary["skipped_no_profile"] == 1
    assert rows == []


def test_quantity_csv_export_writes_expected_headers(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        QuantityRepository(connection).upsert(
            class_code="VALVE",
            item_name="VALVE",
            unit="pcs",
            quantity=1,
            quantity_method="count_by_object",
        )
        output = CsvExporter(connection).export_quantities(tmp_path / "quantities.csv")

    with output.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        assert {
            "class_code",
            "discipline",
            "item_name",
            "spec",
            "unit",
            "quantity",
            "quantity_method",
            "group_key",
            "status",
            "confidence",
        } <= set(reader.fieldnames or [])


def test_cli_quantity_flow_after_sample_import(tmp_path):
    db_path = tmp_path / "cli.db"
    output_path = tmp_path / "quantities.csv"
    env = os.environ.copy()
    env["DWG_REC_DB"] = str(db_path)

    commands = [
        ["init-db"],
        ["seed-taxonomy"],
        ["import-json", "--input", "samples/demo_parsed.json", "--strict-taxonomy"],
        ["generate-quantities"],
    ]
    for command in commands:
        result = subprocess.run(
            [sys.executable, "-m", "dwg_rec_system.cli", *command],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            check=True,
            text=True,
            capture_output=True,
        )
    summary = json.loads(result.stdout)
    assert summary["created"] >= 2

    list_result = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-quantities"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    rows = json.loads(list_result.stdout)
    assert {row["class_code"] for row in rows} >= {"CONTROL_PANEL", "DDC"}

    subprocess.run(
        [
            sys.executable,
            "-m",
            "dwg_rec_system.cli",
            "export-quantities-csv",
            "--output",
            str(output_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert output_path.exists()
