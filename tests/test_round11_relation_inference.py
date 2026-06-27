import json
import os
import subprocess
import sys
from pathlib import Path

from dwg_rec_system.db import init_database, session
from dwg_rec_system.importers.normalized_json import NormalizedJsonImporter
from dwg_rec_system.repositories import RelationCandidateRepository
from dwg_rec_system.services.relation_engine import RelationEngine
from dwg_rec_system.services.rules import RuleTemplateSeeder
from dwg_rec_system.services.taxonomy import TaxonomySeeder
from dwg_rec_system.spatial import (
    bbox_area,
    bbox_center_distance,
    bbox_intersection,
    containment_ratio,
    is_valid_bbox,
    overlap_ratios,
)


ROOT = Path(__file__).resolve().parents[1]
ROUND11_OBJECTS = ROOT / "samples" / "demo_round11_relations.json"
ROUND11_RULES = ROOT / "samples" / "demo_round11_rules.json"


def test_bbox_helpers_are_deterministic():
    outer = {"min_x": 0, "min_y": 0, "max_x": 100, "max_y": 100}
    inner = {"min_x": 10, "min_y": 20, "max_x": 30, "max_y": 60}
    partial = {"min_x": 20, "min_y": 40, "max_x": 120, "max_y": 140}
    invalid = {"min_x": 5, "min_y": 5, "max_x": 5, "max_y": 9}

    assert is_valid_bbox(outer)
    assert not is_valid_bbox(invalid)
    assert bbox_area(inner) == 800
    assert bbox_intersection(outer, partial) == {
        "min_x": 20.0,
        "min_y": 40.0,
        "max_x": 100.0,
        "max_y": 100.0,
    }
    assert containment_ratio(outer, inner) == 1.0
    assert overlap_ratios(outer, partial) == {
        "overlap_area": 4800.0,
        "source_overlap_ratio": 0.48,
        "target_overlap_ratio": 0.48,
    }
    assert bbox_center_distance(outer, inner) == 31.622777


def test_round11_inference_creates_pending_candidates_with_evidence(tmp_path):
    db_path = tmp_path / "round11.db"
    init_database(db_path)

    with session(db_path) as connection:
        TaxonomySeeder(connection).seed_file()
        NormalizedJsonImporter(connection, strict_taxonomy=True).import_file(ROUND11_OBJECTS)
        RuleTemplateSeeder(connection).seed_file(ROUND11_RULES)

        inferred = RelationEngine(connection).infer()
        candidates = RelationCandidateRepository(connection).list()

        assert len(inferred) == 4
        assert len(candidates) == 4
        assert {candidate["relation_type"] for candidate in candidates} == {
            "contains",
            "located_in",
            "overlaps",
            "labels",
        }
        assert {candidate["status"] for candidate in candidates} == {"pending"}

        evidence_by_type = {
            candidate["relation_type"]: json.loads(candidate["evidence_json"])
            for candidate in candidates
        }
        assert evidence_by_type["contains"]["strategy"] == "bbox_containment"
        assert evidence_by_type["contains"]["containment_ratio"] == 1.0
        assert evidence_by_type["overlaps"]["strategy"] == "bbox_overlap"
        assert evidence_by_type["overlaps"]["overlap_area"] > 0
        assert evidence_by_type["labels"]["strategy"] == "text_label_binding"
        assert evidence_by_type["labels"]["label_text"] == "CP-01"

        RelationEngine(connection).infer()
        candidates_after = RelationCandidateRepository(connection).list()
        assert len(candidates_after) == 4

        relations_count = connection.execute("SELECT COUNT(*) AS cnt FROM relation").fetchone()["cnt"]
        assert relations_count == 0


def test_round11_inference_skips_invalid_geometry(tmp_path):
    db_path = tmp_path / "invalid.db"
    init_database(db_path)
    payload = {
        "version": "0.1",
        "drawing": {"drawing_no": "INVALID", "source_file": "invalid.dwg"},
        "objects": [
            {
                "class_name": "ROOM",
                "source_file": "invalid.dwg",
                "handle": "ROOM01",
                "geometry": {"min_x": 0, "min_y": 0, "max_x": 100, "max_y": 100},
            },
            {
                "class_name": "CONTROL_PANEL",
                "source_file": "invalid.dwg",
                "handle": "BAD01",
                "geometry": {"min_x": 10, "min_y": 10, "max_x": 10, "max_y": 20},
            },
        ],
    }
    rules = {
        "rules": [
            {
                "name": "invalid geometry containment",
                "source_class": "ROOM",
                "target_class": "CONTROL_PANEL",
                "relation_type": "contains",
                "config": {"strategy": "bbox_containment", "threshold": 0.9},
            }
        ]
    }

    with session(db_path) as connection:
        NormalizedJsonImporter(connection).import_data(payload)
        RuleTemplateSeeder(connection).seed_data(rules)
        assert RelationEngine(connection).infer() == []
        assert RelationCandidateRepository(connection).list() == []


def test_round11_cli_acceptance_flow(tmp_path):
    db_path = tmp_path / "round11_cli.db"
    env = os.environ.copy()
    env["DWG_REC_DB"] = str(db_path)

    commands = [
        ["init-db"],
        ["seed-taxonomy"],
        ["import-json", "--input", str(ROUND11_OBJECTS), "--strict-taxonomy"],
        ["seed-rules", "--input", str(ROUND11_RULES)],
        ["infer-relations"],
        ["list-candidates"],
    ]

    for command in commands:
        result = subprocess.run(
            [sys.executable, "-m", "dwg_rec_system.cli", *command],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )

    candidates = json.loads(result.stdout)
    assert len(candidates) == 4
    assert {candidate["status"] for candidate in candidates} == {"pending"}
