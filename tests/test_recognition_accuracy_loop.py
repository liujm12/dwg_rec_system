import json
import os
import subprocess
import sys
from pathlib import Path

from dwg_rec_system.db import init_database, session
from dwg_rec_system.importers.normalized_json import NormalizedJsonImporter
from dwg_rec_system.services.parser_import import ParserImportService
from dwg_rec_system.services.recognition import HypothesisAcceptanceService
from dwg_rec_system.services.relation_engine import RelationEngine
from dwg_rec_system.services.review import (
    ObjectCorrectionService,
    RecognitionEvaluationService,
    ReviewService,
)
from dwg_rec_system.services.rules import RuleTemplateSeeder


ROOT = Path(__file__).resolve().parents[1]
PARSER_SAMPLE = ROOT / "samples" / "demo_parser_output.json"
GROUND_TRUTH = ROOT / "samples" / "demo_ground_truth.json"
ROUND11_OBJECTS = ROOT / "samples" / "demo_round11_relations.json"
ROUND11_RULES = ROOT / "samples" / "demo_round11_rules.json"


def test_review_hypothesis_and_object_corrections_are_audited(tmp_path):
    db_path = tmp_path / "accuracy.db"
    init_database(db_path)

    with session(db_path) as connection:
        summary = ParserImportService(connection).import_file(PARSER_SAMPLE)
        hypothesis_id = summary["recognition"]["hypothesis_ids"][0]

        review_result = ReviewService(connection).review_object_hypothesis(
            hypothesis_id,
            action="accept",
            operator="qa",
            reason="confirmed from sample",
        )
        object_id = review_result["object_id"]
        assert object_id

        corrections = ObjectCorrectionService(connection)
        corrections.correct_class(object_id, "DDC", operator="qa", reason="wrong class")
        corrections.set_attribute(object_id, "tag", "DDC-01", operator="qa", reason="tag correction")
        corrections.correct_bbox(
            object_id,
            {"min_x": 101, "min_y": 102, "max_x": 161, "max_y": 182},
            operator="qa",
            reason="bbox correction",
        )

        logs = connection.execute("SELECT * FROM correction_log").fetchall()
        logged_fields = {(row["entity_type"], row["field_name"]) for row in logs}
        assert logged_fields == {
            ("object_hypothesis", "status"),
            ("object", "class"),
            ("attribute", "default.tag"),
            ("geometry", "bbox"),
        }

        obj = connection.execute("SELECT * FROM cad_object WHERE id = ?", (object_id,)).fetchone()
        assert obj["class"] == "DDC"
        assert obj["status"] == "corrected"


def test_relation_candidate_review_is_audited(tmp_path):
    db_path = tmp_path / "relation_review.db"
    init_database(db_path)

    with session(db_path) as connection:
        NormalizedJsonImporter(connection).import_file(ROUND11_OBJECTS)
        RuleTemplateSeeder(connection).seed_file(ROUND11_RULES)
        RelationEngine(connection).infer()
        candidate = connection.execute(
            "SELECT * FROM relation_candidate WHERE relation_type = 'contains'"
        ).fetchone()

        result = ReviewService(connection).review_relation_candidate(
            candidate["id"],
            action="reject",
            operator="qa",
            reason="not enough evidence",
        )

        assert result["old_status"] == "pending"
        assert result["new_status"] == "rejected"
        log = connection.execute(
            "SELECT * FROM correction_log WHERE entity_type = 'relation_candidate'"
        ).fetchone()
        assert log["entity_id"] == candidate["id"]
        assert log["old_value"] == "pending"
        assert log["new_value"] == "rejected"


def test_recognition_evaluation_report_matches_ground_truth(tmp_path):
    db_path = tmp_path / "evaluation.db"
    init_database(db_path)

    with session(db_path) as connection:
        ParserImportService(connection).import_file(PARSER_SAMPLE)
        report = RecognitionEvaluationService(connection).evaluate_file(GROUND_TRUTH)

        assert report["ground_truth"] == 1
        assert report["predicted"] == 1
        assert report["matched"] == 1
        assert report["false_positive"] == 0
        assert report["false_negative"] == 0
        assert report["precision"] == 1.0
        assert report["recall"] == 1.0
        assert report["by_class"]["CONTROL_PANEL"]["matched"] == 1


def test_accuracy_loop_cli_flow(tmp_path):
    db_path = tmp_path / "accuracy_cli.db"
    env = os.environ.copy()
    env["DWG_REC_DB"] = str(db_path)

    subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "init-db"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "dwg_rec_system.cli",
            "import-parser-output",
            "--input",
            str(PARSER_SAMPLE),
            "--adapter",
            "sample-json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    hypotheses = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-object-hypotheses"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    hypothesis_id = json.loads(hypotheses.stdout)[0]["id"]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "dwg_rec_system.cli",
            "review-hypothesis",
            hypothesis_id,
            "--action",
            "reject",
            "--operator",
            "qa",
            "--reason",
            "false positive",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    corrections = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-corrections"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(corrections.stdout)[0]["entity_type"] == "object_hypothesis"

    evaluation = subprocess.run(
        [
            sys.executable,
            "-m",
            "dwg_rec_system.cli",
            "evaluate-recognition",
            "--ground-truth",
            str(GROUND_TRUTH),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    report = json.loads(evaluation.stdout)
    assert report["ground_truth"] == 1
    assert report["predicted"] == 1
