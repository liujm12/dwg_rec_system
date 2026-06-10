import json

from dwg_rec_system.db import init_database, session
from dwg_rec_system.importers.normalized_json import NormalizedJsonImporter
from dwg_rec_system.services.object_store import ObjectStore
from dwg_rec_system.services.spatial_index import SpatialIndex


SAMPLE_PAYLOAD = {
    "version": "0.1",
    "project": {
        "code": "TEST",
        "name": "Test Project",
    },
    "drawing": {
        "drawing_no": "T-001",
        "revision": "A",
        "discipline": "Electrical",
        "source_file": "test.dwg",
    },
    "objects": [
        {
            "class_name": "DCC_RACK",
            "handle": "R01",
            "source_file": "test.dwg",
            "geometry": {
                "center_x": 500,
                "center_y": 600,
                "width": 200,
                "height": 300,
            },
            "cad_meta": {
                "layer": "E-EQUIP",
                "block_name": "RACK_BLK",
                "color": "7",
            },
            "attributes": {
                "tag": "RACK-A",
                "vendor": "ACME",
            },
        },
        {
            "class_name": "DCC",
            "handle": "D01",
            "source_file": "test.dwg",
            "geometry": {
                "center_x": 520,
                "center_y": 610,
                "width": 40,
                "height": 50,
                "rotation": 45,
            },
            "cad_meta": {
                "layer": "E-CTRL",
            },
            "attributes": {
                "tag": "DCC-B",
            },
        },
    ],
}


def test_import_creates_objects(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)
        result = importer.import_data(SAMPLE_PAYLOAD)

    assert result["objects_total"] == 2
    assert result["created"] == 2
    assert result["updated"] == 0
    assert result["errors"] == []
    assert result["project_id"] is not None
    assert result["drawing_id"] is not None


def test_import_objects_have_geometry(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)
        result = importer.import_data(SAMPLE_PAYLOAD)

        store = ObjectStore(connection)
        objects = store.list_objects()
        assert len(objects) >= 2

        # Find the rack object and verify its geometry
        rack = [o for o in objects if o["handle"] == "R01"][0]
        detail = store.get_object_detail(rack["id"])
        assert detail["center_x"] == 500
        assert detail["center_y"] == 600
        assert detail["width"] == 200
        assert detail["height"] == 300
        assert detail["layer"] == "E-EQUIP"
        assert detail["block_name"] == "RACK_BLK"

        # Check attributes exist
        attr_dict = {a["key"]: a["value"] for a in detail["attributes"]}
        assert attr_dict["tag"] == "RACK-A"
        assert attr_dict["vendor"] == "ACME"


def test_repeated_import_updates_object(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)

        # First import
        result1 = importer.import_data(SAMPLE_PAYLOAD)
        assert result1["created"] == 2
        assert result1["updated"] == 0

        # Modify the payload: change a geometry value and an attribute
        modified = json.loads(json.dumps(SAMPLE_PAYLOAD))
        modified["objects"][0]["geometry"]["width"] = 250
        modified["objects"][0]["attributes"]["tag"] = "RACK-A-MODIFIED"

        # Second import — same source_file + handle, should update
        result2 = importer.import_data(modified)
        assert result2["created"] == 0
        assert result2["updated"] == 2

        # Verify the update
        store = ObjectStore(connection)
        objects = store.list_objects()
        rack = [o for o in objects if o["handle"] == "R01"][0]
        detail = store.get_object_detail(rack["id"])
        assert detail["width"] == 250
        attr_dict = {a["key"]: a["value"] for a in detail["attributes"]}
        assert attr_dict["tag"] == "RACK-A-MODIFIED"


def test_imported_geometry_spatial_query(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)
        importer.import_data(SAMPLE_PAYLOAD)

        store = ObjectStore(connection)
        objects = store.list_objects()
        dcc = [o for o in objects if o["handle"] == "D01"][0]

        # Spatial query: nearest rack to DCC
        spatial = SpatialIndex(connection)
        nearest = spatial.nearest(dcc["id"], "DCC_RACK")
        assert len(nearest) > 0
        rack = [o for o in objects if o["handle"] == "R01"][0]
        assert nearest[0]["id"] == rack["id"]


def test_import_without_project_or_drawing(tmp_path):
    """Objects should import even without project/drawing sections."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    minimal = {
        "objects": [
            {
                "class_name": "VALVE",
                "source_file": "minimal.dwg",
                "handle": "V01",
                "attributes": {"tag": "VLV-01"},
            }
        ]
    }

    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)
        result = importer.import_data(minimal)
        assert result["objects_total"] == 1
        assert result["created"] == 1
        assert result["errors"] == []

        objects = ObjectStore(connection).list_objects()
        assert objects[0]["handle"] == "V01"
        assert objects[0]["class"] == "VALVE"


def test_import_drawing_source_file_inheritance(tmp_path):
    """Objects without source_file should inherit from drawing."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    payload = {
        "drawing": {
            "drawing_no": "INH-001",
            "source_file": "parent.dwg",
        },
        "objects": [
            {
                "class_name": "VALVE",
                "handle": "V02",
            }
        ],
    }

    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)
        result = importer.import_data(payload)
        assert result["created"] == 1
        assert result["errors"] == []

        objects = ObjectStore(connection).list_objects()
        assert objects[0]["source_file"] == "parent.dwg"


def test_import_object_source_file_overrides_drawing(tmp_path):
    """Object-level source_file should override drawing-level."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    payload = {
        "drawing": {
            "drawing_no": "OVR-001",
            "source_file": "parent.dwg",
        },
        "objects": [
            {
                "class_name": "VALVE",
                "handle": "V03",
                "source_file": "child.dwg",
            }
        ],
    }

    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)
        result = importer.import_data(payload)
        assert result["created"] == 1

        objects = ObjectStore(connection).list_objects()
        assert objects[0]["source_file"] == "child.dwg"


def test_import_missing_class_name(tmp_path):
    """Object without class_name should be reported as error."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    payload = {
        "objects": [
            {
                "handle": "BAD01",
                "source_file": "bad.dwg",
            }
        ]
    }

    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)
        result = importer.import_data(payload)
        assert result["created"] == 0
        assert len(result["errors"]) == 1
        assert "class_name" in result["errors"][0]["error"]


def test_import_missing_source_file(tmp_path):
    """Object without source_file (no drawing-level fallback) should error."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    payload = {
        "objects": [
            {
                "class_name": "VALVE",
                "handle": "V04",
            }
        ]
    }

    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)
        result = importer.import_data(payload)
        assert len(result["errors"]) == 1
        assert "source_file" in result["errors"][0]["error"]


def test_import_missing_handle(tmp_path):
    """Object without handle should error."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    payload = {
        "objects": [
            {
                "class_name": "VALVE",
                "source_file": "no_handle.dwg",
            }
        ]
    }

    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)
        result = importer.import_data(payload)
        assert len(result["errors"]) == 1
        assert "handle" in result["errors"][0]["error"]


def test_import_from_file(tmp_path):
    """Test import_file reads a JSON file from disk."""
    db_path = tmp_path / "test.db"
    json_path = tmp_path / "input.json"
    json_path.write_text(json.dumps(SAMPLE_PAYLOAD), encoding="utf-8")
    init_database(db_path)

    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)
        result = importer.import_file(json_path)

    assert result["objects_total"] == 2
    assert result["created"] == 2


def test_import_missing_objects_key(tmp_path):
    """Payload without 'objects' raises ValueError."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)
        try:
            importer.import_data({"version": "0.1"})
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "objects" in str(exc)


def test_import_objects_not_list(tmp_path):
    """Payload with non-list objects raises ValueError."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        importer = NormalizedJsonImporter(connection)
        try:
            importer.import_data({"objects": "not_a_list"})
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "must be a list" in str(exc)
