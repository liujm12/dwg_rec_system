"""Integration tests: import -> spatial -> relation -> export flow."""

import json
from pathlib import Path

from dwg_rec_system.db import init_database, session
from dwg_rec_system.importers.normalized_json import NormalizedJsonImporter
from dwg_rec_system.models import RuleTemplateInput
from dwg_rec_system.repositories import RelationRepository, seed_rules
from dwg_rec_system.services.exports import CsvExporter
from dwg_rec_system.services.object_store import ObjectStore
from dwg_rec_system.services.relation_engine import RelationEngine
from dwg_rec_system.services.spatial_index import SpatialIndex
from dwg_rec_system.services.taxonomy import TaxonomySeeder


IMPORT_PAYLOAD = {
    "version": "0.1",
    "project": {"code": "INT-TEST", "name": "Integration Test"},
    "drawing": {
        "drawing_no": "INT-001",
        "source_file": "integration.dwg",
    },
    "objects": [
        {
            "class_name": "DCC_RACK",
            "handle": "RACK-A",
            "source_file": "integration.dwg",
            "geometry": {
                "center_x": 500,
                "center_y": 500,
                "width": 200,
                "height": 300,
            },
            "cad_meta": {"layer": "E-EQUIP", "block_name": "RACK_BLK", "color": "7"},
            "attributes": {
                "tag": "RACK-A",
                "vendor": "ACME",
                "io_count": 64,
                "weight_kg": 15.5,
            },
        },
        {
            "class_name": "DCC",
            "handle": "DCC-A",
            "source_file": "integration.dwg",
            "geometry": {
                "center_x": 530,
                "center_y": 520,
                "width": 40,
                "height": 50,
            },
            "cad_meta": {"layer": "E-CTRL", "color": "3"},
            "attributes": {
                "tag": "DCC-A",
                "vendor": "Siemens",
                "model": "S7-1500",
            },
        },
    ],
}


# ---------------------------------------------------------------------------
# Attribute value type tests
# ---------------------------------------------------------------------------

def test_attribute_preserves_string_type(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)
        importer.import_data(IMPORT_PAYLOAD)

        row = connection.execute(
            "SELECT value, value_type FROM attribute WHERE key = 'tag' AND value = 'RACK-A'"
        ).fetchone()
        assert row is not None
        assert row["value_type"] == "str"
        assert row["value"] == "RACK-A"


def test_attribute_preserves_integer_type(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)
        importer.import_data(IMPORT_PAYLOAD)

        row = connection.execute(
            "SELECT value, value_type FROM attribute WHERE key = 'io_count'"
        ).fetchone()
        assert row is not None
        assert row["value_type"] == "int"
        assert row["value"] == "64"


def test_attribute_preserves_float_type(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)
        importer.import_data(IMPORT_PAYLOAD)

        row = connection.execute(
            "SELECT value, value_type FROM attribute WHERE key = 'weight_kg'"
        ).fetchone()
        assert row is not None
        assert row["value_type"] == "float"
        assert row["value"] == "15.5"


def test_attribute_preserves_json_type(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)
        payload = {
            "objects": [
                {
                    "class_name": "VALVE",
                    "source_file": "json_test.dwg",
                    "handle": "V-JSON",
                    "attributes": {
                        "tags": ["VLV-01", "VLV-02"],
                        "config": {"size": "DN100", "pressure": "PN16"},
                    },
                }
            ]
        }
        importer.import_data(payload)

        row = connection.execute(
            "SELECT value, value_type FROM attribute WHERE key = 'tags'"
        ).fetchone()
        assert row is not None
        assert row["value_type"] == "json"
        parsed = json.loads(row["value"])
        assert parsed == ["VLV-01", "VLV-02"]

        row2 = connection.execute(
            "SELECT value, value_type FROM attribute WHERE key = 'config'"
        ).fetchone()
        assert row2 is not None
        assert row2["value_type"] == "json"


# ---------------------------------------------------------------------------
# Full pipeline: import -> taxonomy -> relation inference -> CSV export
# ---------------------------------------------------------------------------

def test_full_pipeline_import_infer_export(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        # 1. Seed taxonomy
        TaxonomySeeder(connection).seed_data({
            "object_classes": [
                {"code": "DCC", "name_cn": "DCC控制器", "discipline": "ELECTRICAL"},
                {"code": "DCC_RACK", "name_cn": "DCC机柜", "discipline": "ELECTRICAL"},
            ]
        })

        # 2. Import objects
        result = NormalizedJsonImporter(connection).import_data(IMPORT_PAYLOAD)
        assert result["created"] == 2
        assert result["errors"] == []

        # 3. Verify spatial index works on imported data
        objects = ObjectStore(connection).list_objects()
        dcc = [o for o in objects if o["handle"] == "DCC-A"][0]
        rack = [o for o in objects if o["handle"] == "RACK-A"][0]
        nearest = SpatialIndex(connection).nearest(dcc["id"], "DCC_RACK")
        assert len(nearest) == 1
        assert nearest[0]["id"] == rack["id"]
        assert nearest[0]["class"] == "DCC_RACK"

        # 4. Seed rules and run relation inference
        seed_rules(
            connection,
            [
                RuleTemplateInput(
                    name="DCC mounted on DCC_RACK",
                    source_class="DCC",
                    target_class="DCC_RACK",
                    relation_type="mounted_on",
                    max_distance=100,
                    min_confidence=0.5,
                    priority=10,
                )
            ],
        )

        inferred = RelationEngine(connection).infer()
        assert len(inferred) == 1
        assert inferred[0]["relation_type"] == "mounted_on"

        # Verify candidate → relation chain
        candidates = connection.execute(
            "SELECT * FROM relation_candidate"
        ).fetchall()
        assert len(candidates) == 1
        assert candidates[0]["status"] == "accepted"

        relations = RelationRepository(connection).list()
        assert len(relations) == 1
        assert relations[0]["candidate_id"] == candidates[0]["id"]

        # 5. CSV export works after import
        output_path = tmp_path / "objects.csv"
        exported = CsvExporter(connection).export_objects(output_path)
        assert exported.exists()
        content = exported.read_text(encoding="utf-8-sig")
        assert "DCC_RACK" in content
        assert "DCC" in content
        assert "RACK-A" in content
        assert "DCC-A" in content

        # CSV has header + 2 data rows
        lines = content.strip().split("\n")
        assert len(lines) == 3


def test_relation_inference_after_reimport(tmp_path):
    """Import, infer, re-import with changes, verify inference still works."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        # Seed taxonomy + rules
        TaxonomySeeder(connection).seed_data({
            "object_classes": [
                {"code": "DCC", "name_cn": "DCC控制器", "discipline": "ELECTRICAL"},
                {"code": "DCC_RACK", "name_cn": "DCC机柜", "discipline": "ELECTRICAL"},
            ]
        })
        seed_rules(
            connection,
            [
                RuleTemplateInput(
                    name="DCC to RACK",
                    source_class="DCC",
                    target_class="DCC_RACK",
                    relation_type="mounted_on",
                    max_distance=100,
                    min_confidence=0.5,
                )
            ],
        )

        # First import + infer
        NormalizedJsonImporter(connection).import_data(IMPORT_PAYLOAD)
        RelationEngine(connection).infer()
        candidates_before = connection.execute(
            "SELECT COUNT(*) AS cnt FROM relation_candidate"
        ).fetchone()["cnt"]
        assert candidates_before == 1

        # Re-import with same data (idempotent update)
        result = NormalizedJsonImporter(connection).import_data(IMPORT_PAYLOAD)
        assert result["updated"] == 2

        # Re-infer — should be idempotent on relation candidates
        RelationEngine(connection).infer()
        candidates_after = connection.execute(
            "SELECT COUNT(*) AS cnt FROM relation_candidate"
        ).fetchone()["cnt"]
        assert candidates_after == 1  # no duplicate


def test_full_pipeline_without_geometry(tmp_path):
    """Objects without geometry should import but not participate in spatial inference."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        TaxonomySeeder(connection).seed_data({
            "object_classes": [
                {"code": "TEXT_LABEL", "name_cn": "文本标签", "discipline": "GENERAL"},
            ]
        })
        payload = {
            "objects": [
                {
                    "class_name": "TEXT_LABEL",
                    "source_file": "noloc.dwg",
                    "handle": "T01",
                    "attributes": {"text": "Hello"},
                }
            ]
        }
        result = NormalizedJsonImporter(connection).import_data(payload)
        assert result["created"] == 1

        # Object should exist but geometry table may have no matching row
        detail = ObjectStore(connection).get_object_detail(
            connection.execute(
                "SELECT id FROM cad_object WHERE handle = 'T01'"
            ).fetchone()["id"]
        )
        assert detail is not None
        assert detail["center_x"] is None
