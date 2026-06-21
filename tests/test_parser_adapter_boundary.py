import json
import os
import subprocess
import sys
from pathlib import Path

from dwg_rec_system.db import init_database, session
from dwg_rec_system.parsers import available_adapters, get_adapter
from dwg_rec_system.parsers.sample_json import SampleJsonParserAdapter
from dwg_rec_system.services.parser_import import ParserImportService


def _parser_payload(with_missing_ids: bool = False) -> dict:
    entity = {
        "type": "rect",
        "bbox": {"min_x": 1, "min_y": 2, "max_x": 5, "max_y": 8},
        "style": {"layer": "E-BMS"},
    }
    detection = {
        "class_code": "CONTROL_PANEL",
        "confidence": 0.9,
        "bbox": {"min_x": 1, "min_y": 2, "max_x": 5, "max_y": 8},
        "entity_ids": ["box-1"],
        "attributes": {"tag": "CP-01"},
    }
    if not with_missing_ids:
        entity["id"] = "box-1"
        detection["id"] = "det-1"
    return {
        "source": {"uri": "memory://parser.pdf", "type": "pdf", "title": "Parser"},
        "pages": [
            {
                "page_no": 1,
                "width": 100,
                "height": 100,
                "unit": "mm",
                "entities": [entity],
                "detections": [detection],
            }
        ],
    }


def test_sample_json_adapter_outputs_recognition_payload():
    payload = SampleJsonParserAdapter().parse_data(_parser_payload())
    page = payload["pages"][0]

    assert payload["source_document"]["source_uri"] == "memory://parser.pdf"
    assert payload["source_document"]["parser_name"] == "sample_json_adapter"
    assert page["page"]["page_no"] == 1
    assert page["primitives"][0]["source_local_id"] == "box-1"
    assert page["primitives"][0]["primitive_type"] == "rect"
    assert page["candidates"][0]["source_local_id"] == "det-1"
    assert page["candidates"][0]["class_code"] == "CONTROL_PANEL"
    assert page["candidates"][0]["primitive_links"][0]["primitive_source_local_id"] == "box-1"
    assert page["hypotheses"][0]["source_local_id"] == "hyp-det-1"
    assert page["hypotheses"][0]["candidate_links"][0]["candidate_source_local_id"] == "det-1"


def test_sample_json_adapter_generated_ids_are_stable():
    adapter = SampleJsonParserAdapter()
    first = adapter.parse_data(_parser_payload(with_missing_ids=True))
    second = adapter.parse_data(_parser_payload(with_missing_ids=True))

    assert first["pages"][0]["primitives"][0]["source_local_id"] == second["pages"][0]["primitives"][0]["source_local_id"]
    assert first["pages"][0]["candidates"][0]["source_local_id"] == second["pages"][0]["candidates"][0]["source_local_id"]
    assert first["pages"][0]["hypotheses"][0]["source_local_id"] == second["pages"][0]["hypotheses"][0]["source_local_id"]


def test_sample_json_adapter_ignores_missing_entity_links_deterministically():
    payload = _parser_payload()
    payload["pages"][0]["detections"][0]["entity_ids"] = ["box-1", "missing-1"]
    converted = SampleJsonParserAdapter().parse_data(payload)
    candidate = converted["pages"][0]["candidates"][0]

    assert [link["primitive_source_local_id"] for link in candidate["primitive_links"]] == ["box-1"]
    assert candidate["evidence"]["missing_entity_ids"] == ["missing-1"]


def test_sample_json_adapter_validation_errors():
    adapter = SampleJsonParserAdapter()
    try:
        adapter.parse_data({"pages": []})
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "source.uri" in str(exc)

    try:
        adapter.parse_data({"source": {"uri": "memory://x"}})
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "pages list" in str(exc)


def test_parser_import_service_creates_recognition_records_without_objects(tmp_path):
    db_path = tmp_path / "test.db"
    input_path = tmp_path / "parser.json"
    input_path.write_text(json.dumps(_parser_payload()), encoding="utf-8")
    init_database(db_path)

    with session(db_path) as connection:
        first = ParserImportService(connection).import_file(input_path)
        second = ParserImportService(connection).import_file(input_path)
        counts = {
            table: connection.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()["cnt"]
            for table in [
                "source_document",
                "drawing_page",
                "drawing_primitive",
                "recognition_candidate",
                "object_hypothesis",
                "cad_object",
            ]
        }

    assert first["adapter_name"] == "sample-json"
    assert first["recognition"]["hypotheses_created"] == 1
    assert second["recognition"]["hypotheses_created"] == 1
    assert counts == {
        "source_document": 1,
        "drawing_page": 1,
        "drawing_primitive": 1,
        "recognition_candidate": 1,
        "object_hypothesis": 1,
        "cad_object": 0,
    }


def test_unsupported_parser_adapter_raises(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        try:
            ParserImportService(connection).import_file("missing.json", adapter_name="unknown")
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "unsupported parser adapter" in str(exc)


def test_available_parser_adapters_include_sample_json():
    adapters = available_adapters()

    assert adapters == [
        {
            "adapter_name": "sample-json",
            "parser_name": "sample_json_adapter",
            "parser_version": "0.1",
            "source_type": "json",
        }
    ]
    assert get_adapter("sample-json").adapter_name == "sample-json"


def test_cli_parser_adapter_flow(tmp_path):
    db_path = tmp_path / "cli.db"
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
    adapters = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-parser-adapters"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(adapters.stdout)[0]["adapter_name"] == "sample-json"

    imported = subprocess.run(
        [
            sys.executable,
            "-m",
            "dwg_rec_system.cli",
            "import-parser-output",
            "--input",
            "samples/demo_parser_output.json",
            "--adapter",
            "sample-json",
        ],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    summary = json.loads(imported.stdout)
    assert summary["recognition"]["candidates_created"] == 1
    assert summary["recognition"]["hypotheses_created"] == 1

    candidates = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-recognition-candidates"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert len(json.loads(candidates.stdout)) == 1

    hypotheses = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-object-hypotheses"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert len(json.loads(hypotheses.stdout)) == 1

    objects = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-objects"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(objects.stdout) == []
