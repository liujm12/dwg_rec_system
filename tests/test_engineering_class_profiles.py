import json
from pathlib import Path


BASE_TAXONOMY_PATH = Path("dwg_rec_system/taxonomy/cad_object_taxonomy.json")
PROFILE_PATH = Path("dwg_rec_system/taxonomy/engineering_class_profiles.json")
REQUIRED_PROFILE_GROUPS = {"HVAC", "PIPING", "ELEC", "BMS", "CLEANROOM"}
APPROVED_QUANTITY_METHODS = {
    "count_by_object",
    "length_by_geometry",
    "area_by_geometry",
    "grouped_count",
    "formula",
    "manual_review",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_cad_object_taxonomy_is_general_base_taxonomy():
    taxonomy = load_json(BASE_TAXONOMY_PATH)
    object_classes = taxonomy["object_classes"]
    disciplines = {item["discipline"] for item in object_classes}

    assert taxonomy["domain"] == "cad_object_taxonomy"
    assert len(object_classes) >= 160
    assert {"HVAC", "PIPING", "ELEC", "BMS", "GENERAL"} <= disciplines


def test_engineering_class_profile_shape_is_valid():
    profile = load_json(PROFILE_PATH)
    class_profiles = profile["class_profiles"]
    codes = [item["code"] for item in class_profiles]
    groups = {item["profile_group"] for item in class_profiles}

    assert profile["domain"] == "engineering_class_profiles"
    assert profile["base_taxonomy"] == "cad_object_taxonomy.json"
    assert isinstance(class_profiles, list)
    assert len(class_profiles) >= 25
    assert len(codes) == len(set(codes))
    assert REQUIRED_PROFILE_GROUPS <= groups

    for group in REQUIRED_PROFILE_GROUPS:
        assert sum(1 for item in class_profiles if item["profile_group"] == group) >= 5

    for item in class_profiles:
        assert item["code"]
        assert item["profile_group"] in REQUIRED_PROFILE_GROUPS
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


def test_engineering_class_profiles_reference_existing_taxonomy_codes():
    taxonomy = load_json(BASE_TAXONOMY_PATH)
    profile = load_json(PROFILE_PATH)
    taxonomy_codes = {item["code"] for item in taxonomy["object_classes"]}
    profile_codes = {item["code"] for item in profile["class_profiles"]}

    assert profile_codes <= taxonomy_codes


def test_engineering_class_profiles_declares_approved_quantity_methods():
    profile = load_json(PROFILE_PATH)
    declared = set(profile["approved_quantity_methods"])

    assert declared == APPROVED_QUANTITY_METHODS
