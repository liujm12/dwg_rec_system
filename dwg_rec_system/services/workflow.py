from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any

from ..repositories import (
    WorkflowIssueRepository,
    WorkflowPlanRepository,
    WorkflowStepRepository,
)


ACTIVE_TASK_STATUSES = ("auto", "review", "ready", "blocked", "corrected")
ACTIVE_DEPENDENCY_STATUSES = ("auto", "review", "corrected")


class WorkflowGraphBuilder:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def build(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
        discipline: str | None = None,
        work_package: str | None = None,
        location: str | None = None,
        system_code: str | None = None,
    ) -> dict[str, Any]:
        tasks = self._load_tasks(
            project_id=project_id,
            drawing_id=drawing_id,
            discipline=discipline,
            work_package=work_package,
            location=location,
            system_code=system_code,
        )
        task_ids = {task["id"] for task in tasks}
        dependencies = self._load_dependencies(task_ids)

        predecessors: dict[str, list[str]] = {task_id: [] for task_id in task_ids}
        successors: dict[str, list[str]] = {task_id: [] for task_id in task_ids}
        dependency_ids_by_successor: dict[str, list[str]] = defaultdict(list)
        dependency_ids_by_task: dict[str, list[str]] = defaultdict(list)
        issues: list[dict[str, Any]] = []

        for dependency in dependencies:
            predecessor_id = dependency["predecessor_task_id"]
            successor_id = dependency["successor_task_id"]
            if predecessor_id not in task_ids or successor_id not in task_ids:
                issues.append(
                    {
                        "severity": "warning",
                        "category": "missing_dependency_task",
                        "code": "DEPENDENCY_OUT_OF_SCOPE",
                        "message": "Dependency references a task outside the workflow scope.",
                        "task_id": successor_id if successor_id in task_ids else predecessor_id,
                        "dependency_id": dependency["id"],
                        "evidence": {
                            "predecessor_task_id": predecessor_id,
                            "successor_task_id": successor_id,
                        },
                    }
                )
                continue
            predecessors[successor_id].append(predecessor_id)
            successors[predecessor_id].append(successor_id)
            dependency_ids_by_successor[successor_id].append(dependency["id"])
            dependency_ids_by_task[successor_id].append(dependency["id"])
            dependency_ids_by_task[predecessor_id].append(dependency["id"])
            if dependency["status"] == "review":
                issues.append(
                    {
                        "severity": "warning",
                        "category": "review_dependency",
                        "code": "DEPENDENCY_NEEDS_REVIEW",
                        "message": "Installation dependency needs review before workflow order is trusted.",
                        "task_id": successor_id,
                        "dependency_id": dependency["id"],
                        "evidence": {
                            "predecessor_task_id": predecessor_id,
                            "successor_task_id": successor_id,
                            "dependency_type": dependency["dependency_type"],
                            "reason": dependency.get("reason"),
                        },
                    }
                )

        ordered_task_ids, cycle_task_ids = self._topological_order(tasks, predecessors, successors)
        cycles = [cycle_task_ids] if cycle_task_ids else []
        for task_id in cycle_task_ids:
            issues.append(
                {
                    "severity": "error",
                    "category": "cycle",
                    "code": "WORKFLOW_CYCLE",
                    "message": "Task is involved in a dependency cycle and cannot be ordered deterministically.",
                    "task_id": task_id,
                    "dependency_id": None,
                    "evidence": {
                        "cycle_task_ids": cycle_task_ids,
                        "predecessor_task_ids": sorted(predecessors.get(task_id, [])),
                        "successor_task_ids": sorted(successors.get(task_id, [])),
                    },
                }
            )

        return {
            "tasks": tasks,
            "dependencies": dependencies,
            "predecessors": {key: sorted(value) for key, value in predecessors.items()},
            "successors": {key: sorted(value) for key, value in successors.items()},
            "dependency_ids_by_successor": {
                key: sorted(value) for key, value in dependency_ids_by_successor.items()
            },
            "dependency_ids_by_task": {
                key: sorted(value) for key, value in dependency_ids_by_task.items()
            },
            "issues": issues,
            "cycles": cycles,
            "ordered_task_ids": ordered_task_ids,
            "cycle_task_ids": cycle_task_ids,
        }

    def _load_tasks(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
        discipline: str | None = None,
        work_package: str | None = None,
        location: str | None = None,
        system_code: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions = [f"status IN ({','.join('?' for _ in ACTIVE_TASK_STATUSES)})"]
        params: list[Any] = list(ACTIVE_TASK_STATUSES)
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if drawing_id:
            conditions.append("drawing_id = ?")
            params.append(drawing_id)
        if discipline:
            conditions.append("discipline = ?")
            params.append(discipline)
        if work_package:
            conditions.append("work_package = ?")
            params.append(work_package)
        if location:
            conditions.append("location = ?")
            params.append(location)
        if system_code:
            conditions.append("system_code = ?")
            params.append(system_code)
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM install_task
            WHERE {' AND '.join(conditions)}
            ORDER BY discipline, work_package, location, system_code, class_code, task_name, id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def _load_dependencies(self, task_ids: set[str]) -> list[dict[str, Any]]:
        if not task_ids:
            return []
        placeholders = ",".join("?" for _ in task_ids)
        status_placeholders = ",".join("?" for _ in ACTIVE_DEPENDENCY_STATUSES)
        params = list(ACTIVE_DEPENDENCY_STATUSES) + list(task_ids) + list(task_ids)
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM install_dependency
            WHERE status IN ({status_placeholders})
              AND (
                  predecessor_task_id IN ({placeholders})
                  OR successor_task_id IN ({placeholders})
              )
            ORDER BY dependency_type, predecessor_task_id, successor_task_id, id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def _topological_order(
        self,
        tasks: list[dict[str, Any]],
        predecessors: dict[str, list[str]],
        successors: dict[str, list[str]],
    ) -> tuple[list[str], list[str]]:
        task_by_id = {task["id"]: task for task in tasks}
        in_degree = {task_id: len(set(predecessors.get(task_id, []))) for task_id in task_by_id}
        ready = sorted(
            [task_id for task_id, degree in in_degree.items() if degree == 0],
            key=lambda task_id: _task_sort_key(task_by_id[task_id]),
        )
        ordered: list[str] = []

        while ready:
            task_id = ready.pop(0)
            ordered.append(task_id)
            for successor_id in sorted(
                set(successors.get(task_id, [])),
                key=lambda item: _task_sort_key(task_by_id[item]),
            ):
                in_degree[successor_id] -= 1
                if in_degree[successor_id] == 0:
                    ready.append(successor_id)
                    ready.sort(key=lambda item: _task_sort_key(task_by_id[item]))

        cycle_task_ids = sorted(
            [task_id for task_id, degree in in_degree.items() if degree > 0],
            key=lambda task_id: _task_sort_key(task_by_id[task_id]),
        )
        return ordered + cycle_task_ids, cycle_task_ids


class WorkflowPlanGenerator:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.plans = WorkflowPlanRepository(connection)
        self.steps = WorkflowStepRepository(connection)
        self.issues = WorkflowIssueRepository(connection)

    def generate(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
        discipline: str | None = None,
        work_package: str | None = None,
        location: str | None = None,
        system_code: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        scope = {
            "project_id": project_id,
            "drawing_id": drawing_id,
            "discipline": discipline,
            "work_package": work_package,
            "location": location,
            "system_code": system_code,
        }
        self.plans.mark_superseded(project_id=project_id, drawing_id=drawing_id, scope=scope)
        plan_id = self.plans.create(
            project_id=project_id,
            drawing_id=drawing_id,
            name=name or "Generated workflow plan",
            scope=scope,
            status="review",
        )

        graph = WorkflowGraphBuilder(self.connection).build(**scope)
        task_by_id = {task["id"]: task for task in graph["tasks"]}
        cycle_task_ids = set(graph["cycle_task_ids"])
        review_task_ids = {task["id"] for task in graph["tasks"] if task["status"] == "review"}
        review_task_ids.update(issue["task_id"] for issue in graph["issues"] if issue.get("task_id"))

        issues_created = 0
        for task_id in sorted(review_task_ids & set(task_by_id), key=lambda item: _task_sort_key(task_by_id[item])):
            task = task_by_id[task_id]
            if task["status"] == "review":
                self.issues.create(
                    plan_id=plan_id,
                    task_id=task_id,
                    severity="warning",
                    category="task_needs_review",
                    code="INSTALL_TASK_NEEDS_REVIEW",
                    message="Installation task is marked for review before workflow planning.",
                    evidence={"task_status": task["status"], "class_code": task["class_code"]},
                )
                issues_created += 1

        for issue in graph["issues"]:
            self.issues.create(
                plan_id=plan_id,
                task_id=issue.get("task_id"),
                dependency_id=issue.get("dependency_id"),
                severity=issue["severity"],
                category=issue["category"],
                code=issue["code"],
                message=issue["message"],
                evidence=issue.get("evidence"),
            )
            issues_created += 1

        blocked_steps = 0
        review_steps = 0
        for sequence_no, task_id in enumerate(graph["ordered_task_ids"], start=1):
            task = task_by_id[task_id]
            predecessors = graph["predecessors"].get(task_id, [])
            successors = graph["successors"].get(task_id, [])
            dependency_ids = graph["dependency_ids_by_task"].get(task_id, [])
            status = "planned"
            if task_id in cycle_task_ids:
                status = "blocked"
                blocked_steps += 1
            elif task_id in review_task_ids:
                status = "review"
                review_steps += 1
            self.steps.create(
                plan_id=plan_id,
                task_id=task_id,
                sequence_no=sequence_no,
                sequence_group=_sequence_group(task),
                discipline=task.get("discipline"),
                work_package=task.get("work_package"),
                location=task.get("location"),
                system_code=task.get("system_code"),
                dependency_count=len(predecessors),
                blocked_by_count=len(predecessors) if status == "blocked" else 0,
                status=status,
                evidence={
                    "task_id": task_id,
                    "dependency_ids": dependency_ids,
                    "predecessor_task_ids": predecessors,
                    "successor_task_ids": successors,
                    "ordering_method": "deterministic_topological_sort",
                },
            )

        if not graph["tasks"]:
            self.issues.create(
                plan_id=plan_id,
                severity="warning",
                category="missing_scope",
                code="NO_INSTALL_TASKS_IN_SCOPE",
                message="No installation tasks matched the workflow planning scope.",
                evidence={"scope": scope},
            )
            issues_created += 1

        issue_rows = self.issues.list(plan_id=plan_id)
        has_error = any(issue["severity"] == "error" for issue in issue_rows)
        if has_error or blocked_steps:
            plan_status = "review"
        elif issue_rows or review_steps:
            plan_status = "review"
        else:
            plan_status = "ready"

        summary = {
            "plan_id": plan_id,
            "tasks_total": len(graph["tasks"]),
            "steps_created": len(graph["ordered_task_ids"]),
            "issues_created": issues_created,
            "blocked_steps": blocked_steps,
            "review_steps": review_steps,
            "cycles": len(graph["cycles"]),
            "status": plan_status,
        }
        self.plans.update_summary(plan_id, summary, plan_status)
        return summary


def _task_sort_key(task: dict[str, Any]) -> tuple[str, str, str, str, str, str, str]:
    return (
        task.get("discipline") or "",
        task.get("work_package") or "",
        task.get("location") or "",
        task.get("system_code") or "",
        task.get("class_code") or "",
        task.get("task_name") or "",
        task["id"],
    )


def _sequence_group(task: dict[str, Any]) -> str:
    return "|".join(
        [
            task.get("discipline") or "<none>",
            task.get("work_package") or "<none>",
            task.get("location") or "<none>",
            task.get("system_code") or "<none>",
        ]
    )
