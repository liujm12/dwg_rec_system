import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from dwg_rec_system.db import init_database, session
from dwg_rec_system.importers.normalized_json import NormalizedJsonImporter
from dwg_rec_system.repositories import QuantityRepository, RelationRepository
from dwg_rec_system.services.data_quality import DataQualityChecker, filter_findings
from dwg_rec_system.services.exports import CsvExporter
from dwg_rec_system.services.quantity import QuantityGenerator
from dwg_rec_system.services.taxonomy import TaxonomySeeder


def _profile_path(tmp_path: Path, profiles: list[dict]) -> Path:
    path = tmp_path / "profiles.json"
    path.write_text(
        json.dumps({"class_profiles": profiles}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _profile(
    code: str,
    method: str = "count_by_object",
    expected_attributes: list[str] | None = None,
    group_by: list[str] | None = None,
    relations: list[str] | None = None,
) -> dict:
    return {
        "code": code,
        "profile_group": "TEST",
        "expected_attributes": expected_attributes or [],
        "relations": relations or [],
        "budget": {
            "unit": "pcs",
            "quantity_method": method,
            "group_by": group_by or [],
        },
    }


def _import_payload(connection, objects: list[dict], code: str = "DQ"):
    return NormalizedJsonImporter(connection).import_data(
        {
            "project": {"code": code, "name": f"{code} Project"},
            "drawing": {"drawing_no": f"{code}-001", "source_file": f"{code}.dwg"},
            "objects": objects,
        }
    )


def _categories(findings: list[dict]) -> set[str]:
    return {item["category"] for item in findings}


def test_missing_expected_and_group_attributes(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(
        tmp_path,
        [
            _profile(
                "VALVE",
                expected_attributes=["tag", "diameter", "material"],
                group_by=["diameter"],
            )
        ],
    )
    init_database(db_path)

    with session(db_path) as connection:
        _import_payload(
            connection,
            [
                {
                    "class_name": "VALVE",
                    "source_file": "DQ.dwg",
                    "handle": "V-01",
                    "attributes": {"tag": "V-01"},
                }
            ],
        )
        findings = DataQualityChecker(connection, profile).check()["findings"]

    diameter = [item for item in findings if item["field_name"] == "diameter"][0]
    material = [item for item in findings if item["field_name"] == "material"][0]
    assert diameter["severity"] == "error"
    assert diameter["code"] == "MISSING_GROUP_ATTRIBUTE"
    assert material["severity"] == "warning"


def test_missing_length_and_area_geometry(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(
        tmp_path,
        [
            _profile("PIPE", method="length_by_geometry"),
            _profile("DUCT", method="area_by_geometry"),
        ],
    )
    init_database(db_path)

    with session(db_path) as connection:
        _import_payload(
            connection,
            [
                {"class_name": "PIPE", "source_file": "DQ.dwg", "handle": "P-01"},
                {"class_name": "DUCT", "source_file": "DQ.dwg", "handle": "D-01"},
            ],
        )
        findings = DataQualityChecker(connection, profile).check()["findings"]

    codes = {item["code"] for item in findings}
    assert "MISSING_LENGTH_GEOMETRY" in codes
    assert "MISSING_AREA_GEOMETRY" in codes


def test_low_confidence_object(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(tmp_path, [_profile("VALVE")])
    init_database(db_path)

    with session(db_path) as connection:
        _import_payload(
            connection,
            [
                {
                    "class_name": "VALVE",
                    "source_file": "DQ.dwg",
                    "handle": "V-01",
                    "confidence": 0.5,
                }
            ],
        )
        findings = DataQualityChecker(connection, profile).check()["findings"]

    assert "low_confidence" in _categories(findings)


def test_manual_review_quantity_creates_finding(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(tmp_path, [_profile("DUCT", method="area_by_geometry")])
    init_database(db_path)

    with session(db_path) as connection:
        _import_payload(
            connection,
            [{"class_name": "DUCT", "source_file": "DQ.dwg", "handle": "D-01"}],
        )
        QuantityGenerator(connection, profile).generate()
        findings = DataQualityChecker(connection, profile).check()["findings"]

    assert "manual_review_quantity" in _categories(findings)


def test_missing_engineering_profile_creates_info_finding(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(tmp_path, [])
    init_database(db_path)

    with session(db_path) as connection:
        _import_payload(
            connection,
            [
                {
                    "class_name": "TEXT_LABEL",
                    "source_file": "DQ.dwg",
                    "handle": "T-01",
                }
            ],
        )
        findings = DataQualityChecker(connection, profile).check()["findings"]

    assert findings[0]["category"] == "missing_profile"
    assert findings[0]["severity"] == "info"


def test_missing_accepted_relation_and_active_relation_satisfies_it(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(
        tmp_path,
        [
            _profile("DDC", relations=["mounted_on"]),
            _profile("CONTROL_PANEL"),
        ],
    )
    init_database(db_path)

    with session(db_path) as connection:
        _import_payload(
            connection,
            [
                {"class_name": "DDC", "source_file": "DQ.dwg", "handle": "D-01"},
                {"class_name": "CONTROL_PANEL", "source_file": "DQ.dwg", "handle": "CP-01"},
            ],
        )
        findings = DataQualityChecker(connection, profile).check()["findings"]
        assert "missing_relation" in _categories(findings)

        rows = connection.execute("SELECT id, class FROM cad_object").fetchall()
        ddc_id = [row["id"] for row in rows if row["class"] == "DDC"][0]
        panel_id = [row["id"] for row in rows if row["class"] == "CONTROL_PANEL"][0]
        RelationRepository(connection).upsert(
            source_id=ddc_id,
            target_id=panel_id,
            relation_type="mounted_on",
            confidence=1.0,
        )
        findings_after = DataQualityChecker(connection, profile).check()["findings"]

    assert "missing_relation" not in _categories(findings_after)


def test_project_and_drawing_filters(tmp_path):
    db_path = tmp_path / "test.db"
    profile = _profile_path(tmp_path, [_profile("VALVE", expected_attributes=["tag"])])
    init_database(db_path)

    with session(db_path) as connection:
        first = _import_payload(
            connection,
            [{"class_name": "VALVE", "source_file": "DQ.dwg", "handle": "V-01"}],
            code="DQ1",
        )
        _import_payload(
            connection,
            [
                {
                    "class_name": "VALVE",
                    "source_file": "DQ2.dwg",
                    "handle": "V-02",
                    "attributes": {"tag": "V-02"},
                }
            ],
            code="DQ2",
        )
        result = DataQualityChecker(connection, profile).check(
            project_id=first["project_id"],
            drawing_id=first["drawing_id"],
        )

    assert result["summary"]["objects_checked"] == 1
    assert result["summary"]["findings_total"] == 1


def test_filter_findings_by_severity_and_category():
    findings = [
        {"severity": "error", "category": "missing_geometry"},
        {"severity": "warning", "category": "missing_attribute"},
    ]

    assert filter_findings(findings, severity="error") == [findings[0]]
    assert filter_findings(findings, category="missing_attribute") == [findings[1]]


def test_quality_csv_export_writes_header_for_empty_findings(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        output = CsvExporter(connection).export_quality_findings(
            tmp_path / "quality.csv",
            [],
        )

    with output.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        assert "severity" in (reader.fieldnames or [])
        assert "evidence" in (reader.fieldnames or [])


def test_quality_csv_export_serializes_nested_evidence(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    finding = {
        "finding_id": "dq_00001",
        "severity": "error",
        "category": "missing_geometry",
        "code": "MISSING_LENGTH_GEOMETRY",
        "message": "missing",
        "evidence": {"expected": ["width", "height"]},
    }

    with session(db_path) as connection:
        output = CsvExporter(connection).export_quality_findings(
            tmp_path / "quality.csv",
            [finding],
        )

    with output.open(encoding="utf-8-sig", newline="") as file:
        row = next(csv.DictReader(file))
    assert json.loads(row["evidence"]) == {"expected": ["width", "height"]}


def test_cli_quality_flow_after_sample_import(tmp_path):
    db_path = tmp_path / "cli.db"
    output_path = tmp_path / "quality_findings.csv"
    env = os.environ.copy()
    env["DWG_REC_DB"] = str(db_path)
    cwd = Path(__file__).resolve().parents[1]

    commands = [
        ["init-db"],
        ["seed-taxonomy"],
        ["import-json", "--input", "samples/demo_parsed.json", "--strict-taxonomy"],
        ["generate-quantities"],
    ]
    for command in commands:
        subprocess.run(
            [sys.executable, "-m", "dwg_rec_system.cli", *command],
            cwd=cwd,
            env=env,
            check=True,
            text=True,
            capture_output=True,
        )

    check_result = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "check-data-quality"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    result = json.loads(check_result.stdout)
    assert result["summary"]["findings_total"] > 0
    assert "missing_attribute" in result["summary"]["by_category"]

    list_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dwg_rec_system.cli",
            "list-quality-findings",
            "--severity",
            "error",
            "--category",
            "missing_attribute",
        ],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    rows = json.loads(list_result.stdout)
    assert rows
    assert {row["severity"] for row in rows} == {"error"}
    assert {row["category"] for row in rows} == {"missing_attribute"}

    subprocess.run(
        [
            sys.executable,
            "-m",
            "dwg_rec_system.cli",
            "export-quality-findings-csv",
            "--output",
            str(output_path),
        ],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert output_path.exists()
