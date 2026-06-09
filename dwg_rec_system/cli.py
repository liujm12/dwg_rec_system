from __future__ import annotations

import argparse
import json
from pathlib import Path

from .db import database_path, init_database, session
from .models import CadMetaInput, GeometryInput, ObjectInput, RuleTemplateInput
from .repositories import (
    DrawingRepository,
    ObjectClassRepository,
    ProjectRepository,
    RelationRepository,
    seed_rules,
)
from .services.exports import CsvExporter
from .services.object_store import ObjectStore
from .services.relation_engine import RelationEngine
from .services.spatial_index import SpatialIndex


def cmd_init_db(_: argparse.Namespace) -> None:
    path = init_database()
    print(f"initialized: {path}")


def cmd_seed_demo(_: argparse.Namespace) -> None:
    init_database()
    with session() as connection:
        project_id = ProjectRepository(connection).get_or_create(
            code="DEMO",
            name="Demo CAD Recognition Project",
        )
        drawing_id = DrawingRepository(connection).get_or_create(
            drawing_no="E-1001",
            revision="C",
            discipline="Electrical",
            sheet="1",
            title="Demo control cabinet layout",
            source_file="demo.dwg",
            project_id=project_id,
        )
        class_repo = ObjectClassRepository(connection)
        rack_class_id = class_repo.get_or_create("DCC_RACK", "DCC Rack", discipline="Electrical")
        dcc_class_id = class_repo.get_or_create("DCC", "DCC Controller", discipline="Electrical")
        store = ObjectStore(connection)
        rack_id = store.create_object(
            ObjectInput(
                class_name="DCC_RACK",
                class_id=rack_class_id,
                subtype="RACK_V1",
                source_file="demo.dwg",
                handle="RACK01",
                drawing_id=drawing_id,
                confidence=0.98,
                parser_name="demo_parser",
                parser_version="0.1",
                recognition_model="rule_demo",
                recognition_version="0.1",
                geometry=GeometryInput(center_x=1000, center_y=2000, width=300, height=500),
                cad_meta=CadMetaInput(layer="E-EQUIP", block_name="DCC_RACK_BLOCK", color="7"),
                attributes={"tag": "RACK-01", "vendor": "Generic"},
            )
        )
        dcc_id = store.create_object(
            ObjectInput(
                class_name="DCC",
                class_id=dcc_class_id,
                subtype="DCC_V2",
                source_file="demo.dwg",
                handle="DCC01",
                drawing_id=drawing_id,
                confidence=0.97,
                parser_name="demo_parser",
                parser_version="0.1",
                recognition_model="rule_demo",
                recognition_version="0.1",
                geometry=GeometryInput(center_x=1040, center_y=2030, width=80, height=120, rotation=90),
                cad_meta=CadMetaInput(layer="E-EQUIP", block_name="DCC_BLOCK", color="3"),
                attributes={"tag": "DCC-001", "vendor": "ABB", "model": "AC800M"},
            )
        )
        seed_rules(
            connection,
            [
                RuleTemplateInput(
                    name="DCC mounted on nearest DCC rack",
                    source_class="DCC",
                    target_class="DCC_RACK",
                    relation_type="mounted_on",
                    max_distance=100,
                    min_confidence=0.6,
                    priority=10,
                )
            ],
        )
    print(json.dumps({"project_id": project_id, "rack_id": rack_id, "dcc_id": dcc_id}, ensure_ascii=False, indent=2))


def cmd_list_objects(args: argparse.Namespace) -> None:
    with session() as connection:
        rows = ObjectStore(connection).list_objects(args.class_name)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_nearest(args: argparse.Namespace) -> None:
    with session() as connection:
        rows = SpatialIndex(connection).nearest(args.object_id, args.target_class, args.limit)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_infer_relations(_: argparse.Namespace) -> None:
    with session() as connection:
        inferred = RelationEngine(connection).infer()
        relations = RelationRepository(connection).list()
    print(json.dumps({"inferred": inferred, "relations": relations}, ensure_ascii=False, indent=2))


def cmd_export_csv(args: argparse.Namespace) -> None:
    with session() as connection:
        output = CsvExporter(connection).export_objects(args.output)
    print(f"exported: {output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CAD drawing recognition system database tools.")
    parser.add_argument("--db", default=None, help="Reserved for future use. Use DWG_REC_DB for now.")
    subparsers = parser.add_subparsers(required=True)

    init_db = subparsers.add_parser("init-db", help="Create database schema.")
    init_db.set_defaults(func=cmd_init_db)

    seed_demo = subparsers.add_parser("seed-demo", help="Insert demo drawing, objects, and rules.")
    seed_demo.set_defaults(func=cmd_seed_demo)

    list_objects = subparsers.add_parser("list-objects", help="List recognized objects.")
    list_objects.add_argument("--class-name")
    list_objects.set_defaults(func=cmd_list_objects)

    nearest = subparsers.add_parser("nearest", help="Find nearest objects.")
    nearest.add_argument("object_id")
    nearest.add_argument("--target-class")
    nearest.add_argument("--limit", type=int, default=5)
    nearest.set_defaults(func=cmd_nearest)

    infer = subparsers.add_parser("infer-relations", help="Run rule-based relation inference.")
    infer.set_defaults(func=cmd_infer_relations)

    export = subparsers.add_parser("export-csv", help="Export object list as CSV.")
    export.add_argument("--output", default=str(Path("exports/objects.csv")))
    export.set_defaults(func=cmd_export_csv)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.db:
        print(f"using environment/default database: {database_path()}")
    args.func(args)


if __name__ == "__main__":
    main()
