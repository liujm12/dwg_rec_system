import json
import os
import subprocess
import sys

from dwg_rec_system.db import init_database, session
from dwg_rec_system.importers.normalized_json import NormalizedJsonImporter
from dwg_rec_system.repositories import RelationCandidateRepository, RelationRepository
from dwg_rec_system.services.relation_engine import RelationEngine
from dwg_rec_system.services.rules import RuleTemplateSeeder
from dwg_rec_system.services.taxonomy import TaxonomySeeder


SAMPLE_OBJECTS = {
    "version": "0.1",
    "project": {"code": "R2", "name": "Round 2"},
    "drawing": {"drawing_no": "R2-001", "source_file": "round2.dwg"},
    "objects": [
        {
            "class_name": "DCC_RACK",
            "source_file": "round2.dwg",
            "handle": "RACK01",
            "geometry": {"center_x": 1000, "center_y": 2000, "width": 300, "height": 500},
        },
        {
            "class_name": "DCC",
            "source_file": "round2.dwg",
            "handle": "DCC01",
            "geometry": {"center_x": 1040, "center_y": 2030, "width": 80, "height": 120},
        },
    ],
}


SAMPLE_RULES = {
    "version": "0.1",
    "rules": [
        {
            "name": "DCC mounted on nearest DCC rack",
            "source_class": "DCC",
            "target_class": "DCC_RACK",
            "relation_type": "mounted_on",
            "max_distance": 100,
            "min_confidence": 0.6,
            "priority": 10,
            "enabled": True,
        }
    ],
}


def seed_minimal_taxonomy(connection):
    TaxonomySeeder(connection).seed_data(
        {
            "object_classes": [
                {"code": "DCC", "name_cn": "DCC Controller", "discipline": "ELECTRICAL"},
                {"code": "DCC_RACK", "name_cn": "DCC Rack", "discipline": "ELECTRICAL"},
            ]
        }
    )


def test_rule_template_seeder_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        seeder = RuleTemplateSeeder(connection)
        first = seeder.seed_data(SAMPLE_RULES)
        second = seeder.seed_data(SAMPLE_RULES)

        assert first["created"] == 1
        assert first["skipped"] == 0
        assert first["errors"] == []
        assert second["created"] == 0
        assert second["skipped"] == 1

        count = connection.execute("SELECT COUNT(*) AS cnt FROM rule_template").fetchone()["cnt"]
        assert count == 1


def test_rule_template_seeder_requires_rules_key(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        try:
            RuleTemplateSeeder(connection).seed_data({"version": "0.1"})
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "rules" in str(exc)


def test_import_rule_infer_creates_mounted_on_relation(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        seed_minimal_taxonomy(connection)
        import_result = NormalizedJsonImporter(connection, strict_taxonomy=True).import_data(SAMPLE_OBJECTS)
        rule_result = RuleTemplateSeeder(connection).seed_data(SAMPLE_RULES)
        inferred = RelationEngine(connection).infer()
        candidates = RelationCandidateRepository(connection).list()
        relations = RelationRepository(connection).list()

        assert import_result["created"] == 2
        assert import_result["errors"] == []
        assert rule_result["created"] == 1
        assert len(inferred) == 1
        assert inferred[0]["relation_type"] == "mounted_on"
        assert len(candidates) == 1
        assert candidates[0]["status"] == "accepted"
        assert len(relations) == 1
        assert relations[0]["candidate_id"] == candidates[0]["id"]


def test_strict_taxonomy_rejects_unknown_class(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    payload = {
        "objects": [
            {
                "class_name": "UNKNOWN_DEVICE",
                "source_file": "unknown.dwg",
                "handle": "U01",
            }
        ]
    }

    with session(db_path) as connection:
        result = NormalizedJsonImporter(connection, strict_taxonomy=True).import_data(payload)

        assert result["created"] == 0
        assert len(result["errors"]) == 1
        assert "unknown class_name" in result["errors"][0]["error"]
        count = connection.execute("SELECT COUNT(*) AS cnt FROM cad_object").fetchone()["cnt"]
        assert count == 0


def test_non_strict_taxonomy_imports_unknown_class(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    payload = {
        "objects": [
            {
                "class_name": "UNKNOWN_DEVICE",
                "source_file": "unknown.dwg",
                "handle": "U01",
            }
        ]
    }

    with session(db_path) as connection:
        result = NormalizedJsonImporter(connection).import_data(payload)

        assert result["created"] == 1
        assert result["errors"] == []
        assert result["auto_created_classes"] == ["UNKNOWN_DEVICE"]


def test_candidate_repository_list_accept_reject(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        seed_minimal_taxonomy(connection)
        NormalizedJsonImporter(connection, strict_taxonomy=True).import_data(SAMPLE_OBJECTS)
        RuleTemplateSeeder(connection).seed_data(SAMPLE_RULES)
        RelationEngine(connection).infer()

        repository = RelationCandidateRepository(connection)
        accepted = repository.list(status="accepted", source="rule", relation_type="mounted_on")
        assert len(accepted) == 1

        relation_id = repository.accept(accepted[0]["id"])
        assert relation_id

        repository.reject(accepted[0]["id"])
        rejected = repository.list(status="rejected")
        assert len(rejected) == 1
        assert rejected[0]["id"] == accepted[0]["id"]

        relations = RelationRepository(connection).list()
        assert len(relations) == 1


def test_round2_cli_commands_print_json(tmp_path):
    db_path = tmp_path / "cli.db"
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps(SAMPLE_RULES), encoding="utf-8")
    env = os.environ.copy()
    env["DWG_REC_DB"] = str(db_path)

    subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "init-db"],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )
    seeded = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "seed-rules", "--input", str(rules_path)],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )
    listed = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-candidates"],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    assert json.loads(seeded.stdout)["created"] == 1
    assert json.loads(listed.stdout) == []
