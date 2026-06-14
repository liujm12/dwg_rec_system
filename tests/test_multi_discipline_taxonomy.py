import json
from pathlib import Path

from dwg_rec_system.db import init_database, session
from dwg_rec_system.services.taxonomy import TaxonomySeeder


TAXONOMY_PATH = Path("dwg_rec_system/taxonomy/multi_discipline_taxonomy.json")
REQUIRED_DISCIPLINES = {"HVAC", "PLUMBING", "ELEC", "BAS_ICA", "CLEANROOM"}
APPROVED_QUANTITY_METHODS = {
    "count_by_object",
    "length_by_geometry",
    "area_by_geometry",
    "grouped_count",
    "formula",
    "manual_review",
}


def load_taxonomy():
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def test_multi_discipline_taxonomy_shape_is_valid():
    taxonomy = load_taxonomy()
    object_classes = taxonomy["object_classes"]
    codes = [item["code"] for item in object_classes]
    disciplines = {item["discipline"] for item in object_classes}

    assert taxonomy["domain"] == "multi_discipline_engineering"
    assert isinstance(object_classes, list)
    assert len(object_classes) >= 50
    assert len(codes) == len(set(codes))
    assert REQUIRED_DISCIPLINES <= disciplines

    for discipline in REQUIRED_DISCIPLINES:
        assert sum(1 for item in object_classes if item["discipline"] == discipline) >= 10

    for item in object_classes:
        assert item["code"]
        assert item["name_cn"]
        assert item["discipline"] in REQUIRED_DISCIPLINES
        assert isinstance(item.get("aliases", []), list)
        assert isinstance(item["expected_attributes"], list)
        assert item["expected_attributes"]
        assert isinstance(item.get("relations", []), list)

        budget = item.get("budget")
        assert budget or item.get("description")
        if budget:
            assert budget["quantity_method"] in APPROVED_QUANTITY_METHODS
            assert budget["unit"]
            assert isinstance(budget.get("group_by", []), list)

        installation = item.get("installation")
        if installation:
            assert installation["work_package"]
            assert isinstance(installation["default_steps"], list)
            assert installation["default_steps"]
            assert isinstance(installation.get("required_predecessors", []), list)


def test_multi_discipline_taxonomy_declares_approved_quantity_methods():
    taxonomy = load_taxonomy()
    declared = set(taxonomy["approved_quantity_methods"])

    assert declared == APPROVED_QUANTITY_METHODS


def test_multi_discipline_taxonomy_seeds_object_classes(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    taxonomy = load_taxonomy()

    with session(db_path) as connection:
        result = TaxonomySeeder(connection).seed_data(taxonomy)

        assert result["created"] == len(taxonomy["object_classes"])
        assert result["skipped"] == 0
        assert result["errors"] == []

        row = connection.execute(
            """
            SELECT code, name, discipline, description
            FROM object_class
            WHERE code = 'PLB_VALVE'
            """
        ).fetchone()
        assert row is not None
        assert row["discipline"] == "PLUMBING"
        assert "diameter" in row["description"]
        assert "method=count_by_object" in row["description"]
        assert "pipe accessory installation" in row["description"]


def test_multi_discipline_taxonomy_seeding_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    taxonomy = load_taxonomy()

    with session(db_path) as connection:
        first = TaxonomySeeder(connection).seed_data(taxonomy)
        second = TaxonomySeeder(connection).seed_data(taxonomy)

        assert first["created"] == len(taxonomy["object_classes"])
        assert second["created"] == 0
        assert second["skipped"] == len(taxonomy["object_classes"])

        count = connection.execute(
            "SELECT COUNT(*) AS cnt FROM object_class"
        ).fetchone()["cnt"]
        assert count == len(taxonomy["object_classes"])
