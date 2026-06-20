import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from dwg_rec_system.db import init_database, session
from dwg_rec_system.repositories import (
    HypothesisToObjectRepository,
    ObjectHypothesisRepository,
    RecognitionCandidateRepository,
    SourceDocumentRepository,
)
from dwg_rec_system.services.exports import CsvExporter
from dwg_rec_system.services.object_store import ObjectStore
from dwg_rec_system.services.recognition import (
    HypothesisAcceptanceService,
    RecognitionImportService,
)
from dwg_rec_system.services.taxonomy import TaxonomySeeder


def _payload() -> dict:
    return {
        "source_document": {
            "source_uri": "memory://demo.pdf",
            "source_type": "pdf",
            "title": "Demo",
            "parser_name": "unit_parser",
            "parser_version": "0.1",
        },
        "pages": [
            {
                "page": {"page_no": 1, "width": 100, "height": 100, "unit": "mm"},
                "primitives": [
                    {
                        "source_local_id": "p1",
                        "primitive_type": "rect",
                        "bbox": {"min_x": 10, "min_y": 20, "max_x": 50, "max_y": 80},
                    },
                    {
                        "source_local_id": "t1",
                        "primitive_type": "text",
                        "text": "CP-01",
                    },
                ],
                "candidates": [
                    {
                        "source_local_id": "c1",
                        "candidate_type": "object",
                        "class_code": "CONTROL_PANEL",
                        "label": "control panel",
                        "confidence": 0.9,
                        "source": "import",
                        "bbox": {"min_x": 10, "min_y": 20, "max_x": 50, "max_y": 80},
                        "attributes": {"tag": "CP-01", "system": "BMS"},
                        "primitive_links": [
                            {"primitive_source_local_id": "p1", "role": "geometry"},
                            {"primitive_source_local_id": "t1", "role": "text"},
                        ],
                    }
                ],
                "hypotheses": [
                    {
                        "source_local_id": "h1",
                        "class_code": "CONTROL_PANEL",
                        "confidence": 0.88,
                        "bbox": {"min_x": 10, "min_y": 20, "max_x": 50, "max_y": 80},
                        "geometry": {"source": "bbox"},
                        "attributes": {"tag": "CP-01", "system": "BMS"},
                        "candidate_links": [
                            {"candidate_source_local_id": "c1", "role": "primary"},
                        ],
                    }
                ],
            }
        ],
    }


def test_recognition_tables_exist_with_expected_columns(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        source_columns = {row["name"] for row in connection.execute("PRAGMA table_info(source_document)").fetchall()}
        primitive_columns = {row["name"] for row in connection.execute("PRAGMA table_info(drawing_primitive)").fetchall()}
        candidate_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(recognition_candidate)").fetchall()
        }
        hypothesis_columns = {row["name"] for row in connection.execute("PRAGMA table_info(object_hypothesis)").fetchall()}
        mapping_columns = {row["name"] for row in connection.execute("PRAGMA table_info(hypothesis_to_object)").fetchall()}

    assert {"id", "source_uri", "source_type", "metadata_json", "status"} <= source_columns
    assert {"id", "page_id", "source_local_id", "primitive_type", "bbox_json"} <= primitive_columns
    assert {"id", "page_id", "source_local_id", "candidate_type", "class_code", "status"} <= candidate_columns
    assert {"id", "page_id", "source_document_id", "class_code", "source_local_id", "status"} <= hypothesis_columns
    assert {"id", "hypothesis_id", "object_id", "acceptance_method"} <= mapping_columns


def test_recognition_import_creates_records_and_links(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        summary = RecognitionImportService(connection).import_data(_payload())
        candidates = RecognitionCandidateRepository(connection).list()
        hypotheses = ObjectHypothesisRepository(connection).list()
        primitive_links = connection.execute(
            "SELECT COUNT(*) AS cnt FROM recognition_candidate_primitive"
        ).fetchone()["cnt"]
        hypothesis_links = connection.execute(
            "SELECT COUNT(*) AS cnt FROM hypothesis_candidate"
        ).fetchone()["cnt"]

    assert summary["pages_created"] == 1
    assert summary["primitives_created"] == 2
    assert summary["candidates_created"] == 1
    assert summary["hypotheses_created"] == 1
    assert primitive_links == 2
    assert hypothesis_links == 1
    assert candidates[0]["status"] == "pending"
    assert hypotheses[0]["status"] == "pending"
    assert json.loads(hypotheses[0]["attributes_json"])["tag"] == "CP-01"


def test_recognition_import_is_idempotent_for_local_ids(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        RecognitionImportService(connection).import_data(_payload())
        RecognitionImportService(connection).import_data(_payload())
        counts = {
            table: connection.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()["cnt"]
            for table in [
                "source_document",
                "drawing_page",
                "drawing_primitive",
                "recognition_candidate",
                "object_hypothesis",
            ]
        }

    assert counts == {
        "source_document": 1,
        "drawing_page": 1,
        "drawing_primitive": 2,
        "recognition_candidate": 1,
        "object_hypothesis": 1,
    }


def test_accept_hypothesis_creates_object_with_geometry_attributes_and_mapping(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        TaxonomySeeder(connection).seed_file()
        summary = RecognitionImportService(connection).import_data(_payload())
        hypothesis_id = summary["hypothesis_ids"][0]
        result = HypothesisAcceptanceService(connection).accept(
            hypothesis_id,
            accepted_by="tester",
            acceptance_method="manual",
        )
        second = HypothesisAcceptanceService(connection).accept(hypothesis_id)
        detail = ObjectStore(connection).get_object_detail(result["object_id"])
        hypothesis = ObjectHypothesisRepository(connection).get(hypothesis_id)
        candidate = RecognitionCandidateRepository(connection).list()[0]
        mapping = HypothesisToObjectRepository(connection).find_by_hypothesis(hypothesis_id)

    assert result["already_accepted"] is False
    assert second["already_accepted"] is True
    assert second["object_id"] == result["object_id"]
    assert detail["class"] == "CONTROL_PANEL"
    assert detail["source_file"] == "memory://demo.pdf"
    assert detail["handle"] == "1:h1"
    assert detail["center_x"] == 30
    assert detail["center_y"] == 50
    assert {item["key"]: item["value"] for item in detail["attributes"]}["tag"] == "CP-01"
    assert hypothesis["status"] == "accepted"
    assert candidate["status"] == "accepted"
    assert mapping["object_id"] == result["object_id"]


def test_rejected_hypothesis_cannot_be_accepted(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        summary = RecognitionImportService(connection).import_data(_payload())
        hypothesis_id = summary["hypothesis_ids"][0]
        ObjectHypothesisRepository(connection).update_status(hypothesis_id, "rejected")
        try:
            HypothesisAcceptanceService(connection).accept(hypothesis_id)
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "rejected hypothesis" in str(exc)


def test_recognition_csv_exports_write_expected_headers(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        RecognitionImportService(connection).import_data(_payload())
        candidates_path = CsvExporter(connection).export_recognition_candidates(
            tmp_path / "candidates.csv"
        )
        hypotheses_path = CsvExporter(connection).export_object_hypotheses(
            tmp_path / "hypotheses.csv"
        )

    with candidates_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        assert {"source_uri", "source_local_id", "candidate_type", "class_code", "status"} <= set(reader.fieldnames or [])
    with hypotheses_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        assert {"source_uri", "source_local_id", "class_code", "status", "object_id"} <= set(reader.fieldnames or [])


def test_cli_recognition_flow(tmp_path):
    db_path = tmp_path / "cli.db"
    candidates_path = tmp_path / "recognition_candidates.csv"
    hypotheses_path = tmp_path / "object_hypotheses.csv"
    env = os.environ.copy()
    env["DWG_REC_DB"] = str(db_path)
    cwd = Path(__file__).resolve().parents[1]

    subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "init-db"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    import_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dwg_rec_system.cli",
            "import-recognition-json",
            "--input",
            "samples/demo_recognition.json",
        ],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    summary = json.loads(import_result.stdout)
    assert summary["hypotheses_created"] == 1

    sources_result = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-source-documents"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert len(json.loads(sources_result.stdout)) == 1

    candidates_result = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-recognition-candidates"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert len(json.loads(candidates_result.stdout)) == 1

    hypotheses_result = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-object-hypotheses"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    hypotheses = json.loads(hypotheses_result.stdout)
    assert len(hypotheses) == 1

    accept_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dwg_rec_system.cli",
            "accept-hypothesis",
            hypotheses[0]["id"],
            "--accepted-by",
            "cli-test",
        ],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(accept_result.stdout)["object_id"]

    objects_result = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-objects"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert len(json.loads(objects_result.stdout)) == 1

    subprocess.run(
        [
            sys.executable,
            "-m",
            "dwg_rec_system.cli",
            "export-recognition-candidates-csv",
            "--output",
            str(candidates_path),
        ],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "dwg_rec_system.cli",
            "export-object-hypotheses-csv",
            "--output",
            str(hypotheses_path),
        ],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert candidates_path.exists()
    assert hypotheses_path.exists()
