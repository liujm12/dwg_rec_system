import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from dwg_rec_system.db import init_database, session
from dwg_rec_system.importers.normalized_json import NormalizedJsonImporter
from dwg_rec_system.repositories import (
    BudgetItemRepository,
    CostItemRepository,
    QuantityRepository,
)
from dwg_rec_system.services.budget import BudgetGenerator
from dwg_rec_system.services.cost_items import CostItemSeeder
from dwg_rec_system.services.exports import CsvExporter
from dwg_rec_system.services.quantity import QuantityGenerator
from dwg_rec_system.services.taxonomy import TaxonomySeeder


def _cost_payload() -> dict:
    return {
        "cost_items": [
            {
                "code": "BMS-DDC-SET",
                "name": "DDC controller",
                "discipline": "BMS",
                "class_code": "DDC",
                "unit": "set",
                "unit_price_material": 800,
                "unit_price_labor": 220,
                "unit_price_machine": 30,
            },
            {
                "code": "BMS-CONTROL-PANEL-SET",
                "name": "Control panel",
                "discipline": "BMS",
                "class_code": "CONTROL_PANEL",
                "unit": "set",
                "unit_price_material": 1000,
                "unit_price_labor": 300,
                "unit_price_machine": 50,
            },
        ]
    }


def test_budget_tables_exist_with_expected_columns(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        cost_columns = {row["name"] for row in connection.execute("PRAGMA table_info(cost_item)").fetchall()}
        budget_columns = {row["name"] for row in connection.execute("PRAGMA table_info(budget_item)").fetchall()}

    assert {"id", "code", "class_code", "unit", "unit_price_material", "status"} <= cost_columns
    assert {"id", "quantity_item_id", "cost_item_id", "total_cost", "status"} <= budget_columns


def test_cost_item_upsert_and_match(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        repo = CostItemRepository(connection)
        first_id = repo.upsert(
            code="COST-1",
            name="Valve",
            class_code="VALVE",
            unit="pcs",
            unit_price_material=10,
        )
        second_id = repo.upsert(
            code="COST-1",
            name="Valve updated",
            class_code="VALVE",
            unit="pcs",
            unit_price_material=12,
        )
        matches = repo.find_matches("VALVE", "pcs")
        rows = repo.list(class_code="VALVE")

    assert first_id == second_id
    assert len(rows) == 1
    assert matches[0]["unit_price_material"] == 12


def test_budget_item_create_and_clear_preserves_corrected(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        repo = BudgetItemRepository(connection)
        auto_id = repo.create(
            item_name="VALVE",
            unit="pcs",
            quantity=1,
            total_cost=10,
            status="matched",
        )
        corrected_id = repo.create(
            item_name="VALVE",
            unit="pcs",
            quantity=1,
            total_cost=11,
            status="corrected",
        )
        cleared = repo.clear_auto()
        rows = repo.list()

    assert cleared == 1
    assert [row["id"] for row in rows] == [corrected_id]
    assert auto_id != corrected_id


def test_cost_item_seeder_is_idempotent_and_validates(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        seeder = CostItemSeeder(connection)
        first = seeder.seed_data(_cost_payload())
        second = seeder.seed_data(_cost_payload())
        bad = seeder.seed_data({"cost_items": [{"code": "BAD"}]})
        rows = CostItemRepository(connection).list()

    assert first["created"] == 2
    assert second["updated"] == 2
    assert len(rows) == 2
    assert len(bad["errors"]) == 1


def test_budget_generator_creates_matched_rows_and_costs(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        cost_id = CostItemRepository(connection).upsert(
            code="BMS-DDC-SET",
            name="DDC controller",
            class_code="DDC",
            unit="set",
            unit_price_material=800,
            unit_price_labor=220,
            unit_price_machine=30,
        )
        qty_id = QuantityRepository(connection).upsert(
            class_code="DDC",
            item_name="DDC",
            unit="set",
            quantity=2,
            quantity_method="count_by_object",
            confidence=0.9,
        )
        summary = BudgetGenerator(connection).generate()
        rows = BudgetItemRepository(connection).list()

    assert summary["matched"] == 1
    assert rows[0]["quantity_item_id"] == qty_id
    assert rows[0]["cost_item_id"] == cost_id
    assert rows[0]["material_cost"] == 1600
    assert rows[0]["labor_cost"] == 440
    assert rows[0]["machine_cost"] == 60
    assert rows[0]["total_cost"] == 2100
    assert rows[0]["status"] == "matched"


def test_budget_generator_creates_unmatched_row(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        QuantityRepository(connection).upsert(
            class_code="UNKNOWN",
            item_name="Unknown",
            unit="pcs",
            quantity=3,
            quantity_method="count_by_object",
            confidence=0.9,
        )
        summary = BudgetGenerator(connection).generate()
        rows = BudgetItemRepository(connection).list()

    assert summary["unmatched"] == 1
    assert rows[0]["status"] == "unmatched"
    assert rows[0]["cost_item_id"] is None
    assert rows[0]["confidence"] == 0.5


def test_manual_review_quantity_generates_review_budget_row(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        CostItemRepository(connection).upsert(
            code="DUCT-M2",
            name="Duct",
            class_code="DUCT",
            unit="m2",
            unit_price_material=100,
        )
        QuantityRepository(connection).upsert(
            class_code="DUCT",
            item_name="DUCT",
            unit="m2",
            quantity=0,
            quantity_method="manual_review",
        )
        BudgetGenerator(connection).generate()
        rows = BudgetItemRepository(connection).list()

    assert rows[0]["status"] == "review"


def test_budget_generation_is_idempotent_for_auto_rows(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        CostItemRepository(connection).upsert(
            code="BMS-DDC-SET",
            name="DDC controller",
            class_code="DDC",
            unit="set",
            unit_price_material=1,
        )
        QuantityRepository(connection).upsert(
            class_code="DDC",
            item_name="DDC",
            unit="set",
            quantity=1,
            quantity_method="count_by_object",
        )
        first = BudgetGenerator(connection).generate()
        second = BudgetGenerator(connection).generate()
        rows = BudgetItemRepository(connection).list()

    assert first["created"] == 1
    assert second["cleared"] == 1
    assert len(rows) == 1


def test_budget_generation_project_filter(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        project_id = connection.execute(
            "INSERT INTO project(id, code, name) VALUES ('p1', 'P1', 'P1') RETURNING id"
        ).fetchone()["id"]
        CostItemRepository(connection).upsert(
            code="BMS-DDC-SET",
            name="DDC controller",
            class_code="DDC",
            unit="set",
            unit_price_material=1,
        )
        QuantityRepository(connection).upsert(
            project_id=project_id,
            class_code="DDC",
            item_name="DDC",
            unit="set",
            quantity=1,
            quantity_method="count_by_object",
        )
        QuantityRepository(connection).upsert(
            class_code="DDC",
            item_name="DDC",
            unit="set",
            quantity=1,
            quantity_method="count_by_object",
        )
        summary = BudgetGenerator(connection).generate(project_id=project_id)
        rows = BudgetItemRepository(connection).list()

    assert summary["quantities_total"] == 1
    assert len(rows) == 1
    assert rows[0]["project_id"] == project_id


def test_budget_evidence_contains_quantity_and_cost_context(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        CostItemRepository(connection).upsert(
            code="BMS-DDC-SET",
            name="DDC controller",
            class_code="DDC",
            unit="set",
        )
        qty_id = QuantityRepository(connection).upsert(
            class_code="DDC",
            item_name="DDC",
            unit="set",
            quantity=1,
            quantity_method="count_by_object",
            evidence={"source": "test"},
        )
        BudgetGenerator(connection).generate()
        row = BudgetItemRepository(connection).list()[0]
        evidence = json.loads(row["evidence_json"])

    assert evidence["quantity_item_id"] == qty_id
    assert evidence["cost_item_code"] == "BMS-DDC-SET"
    assert evidence["matched_fields"] == ["class_code", "unit"]


def test_budget_csv_export_writes_expected_headers(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        BudgetItemRepository(connection).create(
            item_name="DDC",
            unit="set",
            quantity=1,
            total_cost=10,
            status="matched",
        )
        output = CsvExporter(connection).export_budget(tmp_path / "budget.csv")

    with output.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        assert {
            "quantity_item_id",
            "cost_item_id",
            "unit_price_material",
            "material_cost",
            "total_cost",
            "pricing_source",
            "status",
            "confidence",
        } <= set(reader.fieldnames or [])


def test_cli_budget_flow_after_sample_import(tmp_path):
    db_path = tmp_path / "cli.db"
    output_path = tmp_path / "budget.csv"
    env = os.environ.copy()
    env["DWG_REC_DB"] = str(db_path)
    cwd = Path(__file__).resolve().parents[1]

    commands = [
        ["init-db"],
        ["seed-taxonomy"],
        ["import-json", "--input", "samples/demo_parsed.json", "--strict-taxonomy"],
        ["generate-quantities"],
        ["check-data-quality"],
        ["seed-cost-items", "--input", "samples/demo_cost_items.json"],
        ["generate-budget"],
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
    summary = json.loads(result.stdout)
    assert summary["matched"] == 2
    assert summary["total_cost"] == 2400

    cost_result = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-cost-items", "--class-code", "DDC"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert len(json.loads(cost_result.stdout)) == 1

    list_result = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-budget-items", "--status", "matched"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    rows = json.loads(list_result.stdout)
    assert {row["class_code"] for row in rows} == {"CONTROL_PANEL", "DDC"}

    subprocess.run(
        [
            sys.executable,
            "-m",
            "dwg_rec_system.cli",
            "export-budget-csv",
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
