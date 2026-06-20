import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from dwg_rec_system.db import init_database, session
from dwg_rec_system.repositories import (
    InstallDependencyRepository,
    InstallTaskRepository,
    WorkflowIssueRepository,
    WorkflowPlanRepository,
    WorkflowStepRepository,
)
from dwg_rec_system.services.exports import CsvExporter
from dwg_rec_system.services.workflow import WorkflowGraphBuilder, WorkflowPlanGenerator


def _task(connection, name: str, status: str = "auto", discipline: str = "BMS") -> str:
    return InstallTaskRepository(connection).create(
        class_code=name,
        task_name=f"Install {name}",
        discipline=discipline,
        work_package="control installation",
        location="L1",
        system_code="BMS",
        status=status,
    )


def _dependency(connection, predecessor: str, successor: str, status: str = "auto") -> str:
    return InstallDependencyRepository(connection).create(
        predecessor_task_id=predecessor,
        successor_task_id=successor,
        dependency_type="finish_to_start",
        reason="test dependency",
        status=status,
    )


def test_workflow_tables_exist_with_expected_columns(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        plan_columns = {row["name"] for row in connection.execute("PRAGMA table_info(workflow_plan)").fetchall()}
        step_columns = {row["name"] for row in connection.execute("PRAGMA table_info(workflow_step)").fetchall()}
        issue_columns = {row["name"] for row in connection.execute("PRAGMA table_info(workflow_issue)").fetchall()}

    assert {"id", "project_id", "drawing_id", "name", "scope_json", "summary_json", "status"} <= plan_columns
    assert {"id", "plan_id", "task_id", "sequence_no", "sequence_group", "status"} <= step_columns
    assert {"id", "plan_id", "task_id", "severity", "category", "code", "message"} <= issue_columns


def test_workflow_repositories_create_list_and_supersede(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        task_id = _task(connection, "DDC")
        plans = WorkflowPlanRepository(connection)
        scope = {"project_id": None, "drawing_id": None, "discipline": "BMS"}
        old_plan_id = plans.create(name="Old", scope=scope, status="review")
        superseded = plans.mark_superseded(scope=scope)
        new_plan_id = plans.create(name="New", scope=scope, status="ready", summary={"steps": 1})
        step_id = WorkflowStepRepository(connection).create(
            plan_id=new_plan_id,
            task_id=task_id,
            sequence_no=1,
            evidence={"source": "test"},
        )
        issue_id = WorkflowIssueRepository(connection).create(
            plan_id=new_plan_id,
            task_id=task_id,
            severity="warning",
            category="task_needs_review",
            code="TEST",
            message="review",
            evidence={"source": "test"},
        )
        rows = plans.list()
        steps = WorkflowStepRepository(connection).list(plan_id=new_plan_id)
        issues = WorkflowIssueRepository(connection).list(plan_id=new_plan_id)

    assert superseded == 1
    assert {row["id"]: row["status"] for row in rows}[old_plan_id] == "superseded"
    assert {row["id"]: row["status"] for row in rows}[new_plan_id] == "ready"
    assert steps[0]["id"] == step_id
    assert json.loads(steps[0]["evidence_json"]) == {"source": "test"}
    assert issues[0]["id"] == issue_id
    assert json.loads(issues[0]["evidence_json"]) == {"source": "test"}


def test_workflow_graph_builds_edges_and_review_issues(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        panel = _task(connection, "CONTROL_PANEL")
        ddc = _task(connection, "DDC")
        rejected_dep = _dependency(connection, ddc, panel, status="rejected")
        review_dep = _dependency(connection, panel, ddc, status="review")
        graph = WorkflowGraphBuilder(connection).build(discipline="BMS")

    assert rejected_dep not in {item["id"] for item in graph["dependencies"]}
    assert review_dep in {item["id"] for item in graph["dependencies"]}
    assert graph["predecessors"][ddc] == [panel]
    assert graph["successors"][panel] == [ddc]
    assert graph["issues"][0]["category"] == "review_dependency"


def test_workflow_plan_generator_orders_simple_chain(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        panel = _task(connection, "CONTROL_PANEL")
        ddc = _task(connection, "DDC")
        sensor = _task(connection, "TEMPERATURE_SENSOR")
        _dependency(connection, panel, ddc)
        _dependency(connection, ddc, sensor)
        summary = WorkflowPlanGenerator(connection).generate(discipline="BMS")
        steps = WorkflowStepRepository(connection).list(plan_id=summary["plan_id"])

    assert summary["status"] == "ready"
    assert [step["task_id"] for step in steps] == [panel, ddc, sensor]
    assert [step["sequence_no"] for step in steps] == [1, 2, 3]
    assert {step["status"] for step in steps} == {"planned"}


def test_workflow_plan_generator_tie_order_and_filter_scope(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        elec = _task(connection, "LIGHT_FIXTURE", discipline="ELEC")
        ddc = _task(connection, "DDC", discipline="BMS")
        panel = _task(connection, "CONTROL_PANEL", discipline="BMS")
        summary = WorkflowPlanGenerator(connection).generate(discipline="BMS")
        steps = WorkflowStepRepository(connection).list(plan_id=summary["plan_id"])

    assert elec not in {step["task_id"] for step in steps}
    assert [step["task_id"] for step in steps] == [panel, ddc]


def test_workflow_plan_generator_cycles_create_blocked_steps_and_issues(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        first = _task(connection, "A")
        second = _task(connection, "B")
        _dependency(connection, first, second)
        _dependency(connection, second, first)
        summary = WorkflowPlanGenerator(connection).generate()
        steps = WorkflowStepRepository(connection).list(plan_id=summary["plan_id"])
        issues = WorkflowIssueRepository(connection).list(plan_id=summary["plan_id"], category="cycle")

    assert summary["cycles"] == 1
    assert summary["blocked_steps"] == 2
    assert {step["status"] for step in steps} == {"blocked"}
    assert len(issues) == 2
    assert {issue["severity"] for issue in issues} == {"error"}


def test_review_install_task_creates_review_step_and_issue(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        task_id = _task(connection, "DDC", status="review")
        summary = WorkflowPlanGenerator(connection).generate()
        steps = WorkflowStepRepository(connection).list(plan_id=summary["plan_id"])
        issues = WorkflowIssueRepository(connection).list(plan_id=summary["plan_id"], category="task_needs_review")

    assert summary["review_steps"] == 1
    assert steps[0]["task_id"] == task_id
    assert steps[0]["status"] == "review"
    assert len(issues) == 1


def test_workflow_generation_supersedes_matching_previous_plan(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        _task(connection, "DDC")
        first = WorkflowPlanGenerator(connection).generate(discipline="BMS")
        second = WorkflowPlanGenerator(connection).generate(discipline="BMS")
        plans = WorkflowPlanRepository(connection).list()

    statuses = {plan["id"]: plan["status"] for plan in plans}
    assert statuses[first["plan_id"]] == "superseded"
    assert statuses[second["plan_id"]] == "ready"


def test_workflow_csv_export_writes_expected_headers(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        _task(connection, "DDC")
        summary = WorkflowPlanGenerator(connection).generate()
        output = CsvExporter(connection).export_workflow_plan(
            tmp_path / "workflow.csv",
            plan_id=summary["plan_id"],
        )

    with output.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        assert {
            "plan_id",
            "sequence_no",
            "sequence_group",
            "task_id",
            "task_name",
            "class_code",
            "discipline",
            "work_package",
            "location",
            "system_code",
            "dependency_count",
            "blocked_by_count",
            "status",
        } <= set(reader.fieldnames or [])


def test_cli_workflow_flow_after_sample_installation(tmp_path):
    db_path = tmp_path / "cli.db"
    output_path = tmp_path / "workflow.csv"
    env = os.environ.copy()
    env["DWG_REC_DB"] = str(db_path)
    cwd = Path(__file__).resolve().parents[1]

    commands = [
        ["init-db"],
        ["seed-taxonomy"],
        ["import-json", "--input", "samples/demo_parsed.json", "--strict-taxonomy"],
        ["seed-rules", "--input", "samples/demo_rules.json"],
        ["infer-relations"],
        ["generate-install-tasks"],
        ["generate-install-dependencies"],
        ["generate-install-instructions"],
        ["generate-workflow-plan"],
    ]
    for command in commands:
        result = subprocess.run(
            [sys.executable, "-m", "dwg_rec_system.cli", *command],
            cwd=cwd,
            env=env,
            check=True,
            text=True,
            capture_output=True,
        )
    summary = json.loads(result.stdout)
    assert summary["steps_created"] == 2
    assert summary["status"] == "ready"

    plans_result = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-workflow-plans"],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    plans = json.loads(plans_result.stdout)
    assert len(plans) == 1

    steps_result = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-workflow-steps", "--plan-id", summary["plan_id"]],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    steps = json.loads(steps_result.stdout)
    assert [step["class_code"] for step in steps] == ["CONTROL_PANEL", "DDC"]

    issues_result = subprocess.run(
        [sys.executable, "-m", "dwg_rec_system.cli", "list-workflow-issues", "--plan-id", summary["plan_id"]],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(issues_result.stdout) == []

    subprocess.run(
        [
            sys.executable,
            "-m",
            "dwg_rec_system.cli",
            "export-workflow-plan-csv",
            "--plan-id",
            summary["plan_id"],
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
