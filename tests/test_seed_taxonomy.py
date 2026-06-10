from dwg_rec_system.db import init_database, session
from dwg_rec_system.services.taxonomy import TaxonomySeeder


# Minimal taxonomy payload matching the real structure
MINIMAL_TAXONOMY = {
    "version": "0.1",
    "domain": "cleanroom_cad",
    "object_classes": [
        {
            "code": "DCC",
            "name_cn": "DCC控制器",
            "discipline": "ELECTRICAL",
            "parent_code": None,
            "aliases": ["DCC", "控制器"],
            "attributes": ["tag", "vendor", "model"],
            "relations": ["mounted_on", "connected_to"],
        },
        {
            "code": "DCC_RACK",
            "name_cn": "DCC机柜",
            "discipline": "ELECTRICAL",
            "parent_code": "RACK",
            "aliases": ["机柜", "rack"],
            "attributes": ["tag", "vendor", "rack_type"],
            "relations": ["contains", "mounted_on"],
        },
        {
            "code": "VALVE",
            "name_cn": "阀门",
            "discipline": "MECHANICAL",
            "parent_code": None,
            "aliases": ["阀门", "valve"],
            "attributes": ["tag", "diameter", "valve_type"],
            "relations": ["connected_to"],
        },
    ],
}


def test_seed_creates_object_classes(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        seeder = TaxonomySeeder(connection)
        result = seeder.seed_data(MINIMAL_TAXONOMY)

        assert result["total"] == 3
        assert result["created"] == 3
        assert result["skipped"] == 0
        assert result["errors"] == []

        # Verify data in DB
        rows = connection.execute(
            "SELECT code, name, discipline, parent_code, description FROM object_class ORDER BY code"
        ).fetchall()
        assert len(rows) == 3

        dcc = [r for r in rows if r["code"] == "DCC"][0]
        assert dcc["name"] == "DCC控制器"
        assert dcc["discipline"] == "ELECTRICAL"
        assert dcc["parent_code"] is None
        assert "tag" in dcc["description"]
        assert "mounted_on" in dcc["description"]

        rack = [r for r in rows if r["code"] == "DCC_RACK"][0]
        assert rack["parent_code"] == "RACK"


def test_repeated_seeding_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        seeder = TaxonomySeeder(connection)

        # First run
        r1 = seeder.seed_data(MINIMAL_TAXONOMY)
        assert r1["created"] == 3
        assert r1["skipped"] == 0

        # Second run — should skip all
        r2 = seeder.seed_data(MINIMAL_TAXONOMY)
        assert r2["created"] == 0
        assert r2["skipped"] == 3

        # Still only 3 rows
        count = connection.execute("SELECT COUNT(*) AS cnt FROM object_class").fetchone()["cnt"]
        assert count == 3


def test_seed_updates_existing_on_rerun(tmp_path):
    """Rerunning with updated data should update existing records."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        seeder = TaxonomySeeder(connection)
        seeder.seed_data(MINIMAL_TAXONOMY)

        # Modify the taxonomy
        modified = {
            "object_classes": [
                {
                    "code": "DCC",
                    "name_cn": "DCC控制器v2",
                    "discipline": "ELECTRICAL",
                    "parent_code": "DCC_RACK",
                    "aliases": ["DCC V2"],
                    "attributes": ["tag"],
                    "relations": ["mounted_on"],
                }
            ]
        }
        r2 = seeder.seed_data(modified)
        assert r2["created"] == 0
        assert r2["skipped"] == 1

        row = connection.execute(
            "SELECT name, parent_code, description FROM object_class WHERE code = 'DCC'"
        ).fetchone()
        assert row["name"] == "DCC控制器v2"
        assert row["parent_code"] == "DCC_RACK"
        assert "DCC V2" in row["description"]


def test_seed_handles_missing_code(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    bad = {
        "object_classes": [
            {"name_cn": "No Code"},
            {"code": "GOOD", "name_cn": "Good One", "discipline": "TEST"},
        ]
    }

    with session(db_path) as connection:
        seeder = TaxonomySeeder(connection)
        result = seeder.seed_data(bad)
        assert result["created"] == 1
        assert len(result["errors"]) == 1
        assert "missing 'code'" in result["errors"][0]["error"]


def test_seed_from_file(tmp_path):
    """Test seed_file reads from disk."""
    import json

    db_path = tmp_path / "test.db"
    json_path = tmp_path / "taxonomy.json"
    json_path.write_text(json.dumps(MINIMAL_TAXONOMY, ensure_ascii=False), encoding="utf-8")
    init_database(db_path)

    with session(db_path) as connection:
        seeder = TaxonomySeeder(connection)
        result = seeder.seed_file(json_path)
        assert result["total"] == 3
        assert result["created"] == 3
