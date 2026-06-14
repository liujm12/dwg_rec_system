import json
from pathlib import Path


TAXONOMY_PATH = Path("dwg_rec_system/taxonomy/cad_object_taxonomy.json")


def load_taxonomy():
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def test_taxonomy_object_classes_are_structurally_valid():
    taxonomy = load_taxonomy()
    disciplines = {item["code"] for item in taxonomy["disciplines"]}
    object_classes = taxonomy["object_classes"]
    relation_types = set(taxonomy["relation_types"])
    object_codes = [item["code"] for item in object_classes]
    object_code_set = set(object_codes)

    assert taxonomy["domain"] == "cad_object_taxonomy"
    assert len(object_classes) >= 160
    assert len(relation_types) >= 45
    assert len(object_codes) == len(object_code_set)

    for item in object_classes:
        assert item["code"]
        assert item["name_cn"]
        assert item["discipline"] in disciplines
        assert isinstance(item.get("aliases", []), list)
        assert isinstance(item.get("attributes", []), list)
        assert isinstance(item.get("relations", []), list)

        parent_code = item.get("parent_code")
        if parent_code:
            assert parent_code in object_code_set

        for relation in item.get("relations", []):
            assert relation in relation_types


def test_taxonomy_has_expected_cleanroom_core_classes():
    taxonomy = load_taxonomy()
    object_codes = {item["code"] for item in taxonomy["object_classes"]}

    expected_codes = {
        "ROOM",
        "CLEANROOM_PARTITION",
        "FFU",
        "HEPA_FILTER",
        "DUCT",
        "AIR_DAMPER",
        "FIRE_ALARM_PANEL",
        "DISTRIBUTION_PANEL",
        "CABLE_TRAY",
        "NETWORK_SWITCH",
        "GAS_CABINET",
        "VMB",
        "PLC",
        "IO_MODULE",
        "PROCESS_TOOL",
        "UTILITY_POINT",
    }

    assert expected_codes <= object_codes
