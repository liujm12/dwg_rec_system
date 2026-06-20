from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..repositories import (
    InstallDependencyRepository,
    InstallInstructionRepository,
    InstallTaskRepository,
)
from .quantity import DEFAULT_PROFILE_PATH, _stringify_group_value


RELATION_DEPENDENCIES = {
    "mounted_on": ("target_before_source", "finish_to_start"),
    "installed_on": ("target_before_source", "finish_to_start"),
    "powered_by": ("target_before_source", "power_before_commissioning"),
    "controlled_by": ("target_before_source", "finish_to_start"),
    "connected_to": ("source_before_target_review", "start_to_start"),
}


class InstallTaskGenerator:
    def __init__(
        self,
        connection: sqlite3.Connection,
        profile_path: str | Path | None = None,
        low_confidence_threshold: float = 0.8,
    ):
        self.connection = connection
        self.profile_path = Path(profile_path) if profile_path else DEFAULT_PROFILE_PATH
        self.low_confidence_threshold = low_confidence_threshold
        self.tasks = InstallTaskRepository(connection)
        self.profiles = self._load_profiles(self.profile_path)

    def generate_tasks(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> dict[str, Any]:
        cleared = self.tasks.clear_auto(project_id=project_id, drawing_id=drawing_id)
        objects = self._load_objects(project_id=project_id, drawing_id=drawing_id)
        attributes = self._load_attributes([item["id"] for item in objects])
        location_evidence = self._load_location_evidence([item["id"] for item in objects])

        summary = {
            "objects_total": len(objects),
            "created": 0,
            "skipped_no_profile": 0,
            "skipped_no_installation_profile": 0,
            "review": 0,
            "cleared": cleared,
        }

        for obj in objects:
            class_code = obj["class"]
            profile = self.profiles.get(class_code)
            if not profile:
                summary["skipped_no_profile"] += 1
                continue
            installation = profile.get("installation") or {}
            if not installation.get("work_package"):
                summary["skipped_no_installation_profile"] += 1
                continue

            object_attributes = attributes.get(obj["id"], {})
            selected_attributes = {
                "tag": self._attribute_value(object_attributes, "tag"),
                "location": self._attribute_value(object_attributes, "location"),
                "room_no": self._attribute_value(object_attributes, "room_no"),
                "system": self._attribute_value(object_attributes, "system"),
            }
            location = (
                selected_attributes["location"]
                or selected_attributes["room_no"]
                or location_evidence.get(obj["id"])
            )
            status = self._status(obj, installation)
            if status == "review":
                summary["review"] += 1
            task_name = self._task_name(class_code, selected_attributes["tag"])
            self.tasks.create(
                project_id=obj["project_id"],
                drawing_id=obj["drawing_id"],
                object_id=obj["id"],
                class_code=class_code,
                discipline=obj["discipline"],
                task_name=task_name,
                work_package=installation.get("work_package"),
                location=location,
                system_code=selected_attributes["system"],
                confidence=float(obj["confidence"] or 1.0),
                evidence={
                    "source_object_id": obj["id"],
                    "class_code": class_code,
                    "profile_group": profile.get("profile_group"),
                    "installation": installation,
                    "selected_attributes": selected_attributes,
                    "location_evidence": location_evidence.get(obj["id"]),
                    "generator": "install_task_generator",
                    "generator_version": "0.1",
                },
                status=status,
            )
            summary["created"] += 1

        return summary

    def _load_objects(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions = ["o.status != 'rejected'"]
        params: list[Any] = []
        if project_id:
            conditions.append("d.project_id = ?")
            params.append(project_id)
        if drawing_id:
            conditions.append("o.drawing_id = ?")
            params.append(drawing_id)
        rows = self.connection.execute(
            f"""
            SELECT
                o.id,
                o.drawing_id,
                d.project_id,
                o.class,
                o.confidence,
                oc.discipline
            FROM cad_object o
            LEFT JOIN drawing d ON d.id = o.drawing_id
            LEFT JOIN object_class oc ON oc.id = o.class_id
            WHERE {' AND '.join(conditions)}
            ORDER BY o.created_at, o.id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def _load_attributes(self, object_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not object_ids:
            return {}
        placeholders = ",".join("?" for _ in object_ids)
        rows = self.connection.execute(
            f"""
            SELECT object_id, key, value, normalized_value, value_type
            FROM attribute
            WHERE object_id IN ({placeholders})
            """,
            object_ids,
        ).fetchall()
        result: dict[str, dict[str, Any]] = defaultdict(dict)
        for row in rows:
            value: Any = row["normalized_value"] if row["normalized_value"] is not None else row["value"]
            if row["value_type"] == "json" and value:
                value = json.loads(value)
            result[row["object_id"]][row["key"]] = value
        return result

    def _load_location_evidence(self, object_ids: list[str]) -> dict[str, str]:
        if not object_ids:
            return {}
        placeholders = ",".join("?" for _ in object_ids)
        rows = self.connection.execute(
            f"""
            SELECT source_id, target_id
            FROM relation
            WHERE status = 'active'
              AND relation_type = 'located_in'
              AND source_id IN ({placeholders})
            ORDER BY created_at, id
            """,
            object_ids,
        ).fetchall()
        return {row["source_id"]: row["target_id"] for row in rows}

    def _status(self, obj: dict[str, Any], installation: dict[str, Any]) -> str:
        if float(obj["confidence"] or 1.0) < self.low_confidence_threshold:
            return "review"
        if not installation.get("default_steps"):
            return "review"
        return "auto"

    @staticmethod
    def _task_name(class_code: str, tag: str | None) -> str:
        return f"Install {class_code} {tag}" if tag else f"Install {class_code}"

    @staticmethod
    def _attribute_value(attributes: dict[str, Any], key: str) -> str | None:
        value = attributes.get(key)
        if value is None:
            return None
        return _stringify_group_value(value)

    @staticmethod
    def _load_profiles(path: Path) -> dict[str, dict[str, Any]]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {item["code"]: item for item in payload.get("class_profiles", [])}


class InstallDependencyGenerator:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.dependencies = InstallDependencyRepository(connection)

    def generate_dependencies(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> dict[str, Any]:
        cleared = self.dependencies.clear_auto(project_id=project_id, drawing_id=drawing_id)
        tasks = InstallTaskRepository(self.connection).list(
            project_id=project_id,
            drawing_id=drawing_id,
        )
        task_by_object = {task["object_id"]: task for task in tasks if task.get("object_id")}
        relations = self._load_relations(list(task_by_object))
        summary = {
            "relations_checked": len(relations),
            "created": 0,
            "skipped_missing_task": 0,
            "cleared": cleared,
        }

        for relation in relations:
            mapping = RELATION_DEPENDENCIES.get(relation["relation_type"])
            if not mapping:
                continue
            direction, dependency_type = mapping
            source_task = task_by_object.get(relation["source_id"])
            target_task = task_by_object.get(relation["target_id"])
            if not source_task or not target_task:
                summary["skipped_missing_task"] += 1
                continue
            if direction == "target_before_source":
                predecessor = target_task
                successor = source_task
                status = "auto"
            else:
                predecessor = source_task
                successor = target_task
                status = "review"

            self.dependencies.create(
                predecessor_task_id=predecessor["id"],
                successor_task_id=successor["id"],
                dependency_type=dependency_type,
                reason=f"accepted relation: {relation['relation_type']}",
                confidence=float(relation["confidence"] or 1.0),
                evidence={
                    "relation_id": relation["id"],
                    "relation_type": relation["relation_type"],
                    "source_object_id": relation["source_id"],
                    "target_object_id": relation["target_id"],
                    "direction": direction,
                    "generator": "install_dependency_generator",
                    "generator_version": "0.1",
                },
                status=status,
            )
            summary["created"] += 1

        return summary

    def _load_relations(self, object_ids: list[str]) -> list[dict[str, Any]]:
        if not object_ids:
            return []
        placeholders = ",".join("?" for _ in object_ids)
        params = object_ids + object_ids
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM relation
            WHERE status = 'active'
              AND relation_type IN ({','.join('?' for _ in RELATION_DEPENDENCIES)})
              AND (
                  source_id IN ({placeholders})
                  OR target_id IN ({placeholders})
              )
            ORDER BY relation_type, source_id, target_id, id
            """,
            list(RELATION_DEPENDENCIES) + params,
        ).fetchall()
        return [dict(row) for row in rows]


class InstallInstructionGenerator:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.instructions = InstallInstructionRepository(connection)

    def generate_instructions(
        self,
        project_id: str | None = None,
        drawing_id: str | None = None,
    ) -> dict[str, Any]:
        cleared = self.instructions.clear_auto(project_id=project_id, drawing_id=drawing_id)
        tasks = InstallTaskRepository(self.connection).list(
            project_id=project_id,
            drawing_id=drawing_id,
        )
        dependencies = self._dependencies_by_successor([task["id"] for task in tasks])
        summary = {
            "tasks_total": len(tasks),
            "created": 0,
            "cleared": cleared,
        }

        for task in tasks:
            task_dependencies = dependencies.get(task["id"], [])
            source = {
                "task_id": task["id"],
                "dependency_ids": [item["id"] for item in task_dependencies],
                "task_evidence": json.loads(task["evidence_json"]) if task.get("evidence_json") else {},
            }
            text = self._instruction_text(task, task_dependencies, source["task_evidence"])
            self.instructions.create(
                task_id=task["id"],
                instruction_text=text,
                source=source,
            )
            summary["created"] += 1

        return summary

    def _dependencies_by_successor(self, task_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not task_ids:
            return {}
        placeholders = ",".join("?" for _ in task_ids)
        rows = self.connection.execute(
            f"""
            SELECT d.*, pt.task_name AS predecessor_task_name
            FROM install_dependency d
            LEFT JOIN install_task pt ON pt.id = d.predecessor_task_id
            WHERE d.successor_task_id IN ({placeholders})
              AND d.status != 'rejected'
            ORDER BY d.status, d.dependency_type, d.id
            """,
            task_ids,
        ).fetchall()
        result: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            result[row["successor_task_id"]].append(dict(row))
        return result

    @staticmethod
    def _instruction_text(
        task: dict[str, Any],
        dependencies: list[dict[str, Any]],
        evidence: dict[str, Any],
    ) -> str:
        installation = evidence.get("installation") or {}
        default_steps = installation.get("default_steps") or []
        required_predecessors = installation.get("required_predecessors") or []
        lines = [
            f"Task: {task['task_name']}",
            f"Class: {task['class_code']}",
            f"Work package: {task['work_package'] or 'review required'}",
        ]
        if task.get("location"):
            lines.append(f"Location: {task['location']}")
        if task.get("system_code"):
            lines.append(f"System: {task['system_code']}")
        if default_steps:
            lines.append("Steps:")
            for index, step in enumerate(default_steps, start=1):
                lines.append(f"{index}. {step}")
        else:
            lines.append("Steps: review required because profile default steps are missing.")
        if dependencies:
            lines.append("Dependencies:")
            for item in dependencies:
                predecessor = item.get("predecessor_task_name") or item["predecessor_task_id"]
                lines.append(
                    f"- Complete {predecessor} before this task "
                    f"({item['dependency_type']}; {item['reason'] or 'no reason'})"
                )
        if required_predecessors:
            lines.append("Profile prerequisites:")
            for predecessor in required_predecessors:
                lines.append(f"- {predecessor}")
        if task["status"] == "review":
            lines.append("Review note: task is marked for review because confidence is low or profile data is incomplete.")
        return "\n".join(lines)
