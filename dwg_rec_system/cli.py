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
    RelationCandidateRepository,
    RelationRepository,
    seed_rules,
)
from .importers.normalized_json import NormalizedJsonImporter
from .services.exports import CsvExporter
from .services.object_store import ObjectStore
from .services.relation_engine import RelationEngine
from .services.rules import RuleTemplateSeeder
from .services.spatial_index import SpatialIndex
from .services.taxonomy import TaxonomySeeder


def cmd_init_db(_: argparse.Namespace) -> None:
    path = init_database()
    print(f"initialized: {path}")


def cmd_seed_taxonomy(_: argparse.Namespace) -> None:
    with session() as connection:
        seeder = TaxonomySeeder(connection)
        result = seeder.seed_file()
    print(json.dumps(result, ensure_ascii=False, indent=2))


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


def cmd_import_json(args: argparse.Namespace) -> None:
    with session() as connection:
        importer = NormalizedJsonImporter(connection, strict_taxonomy=args.strict_taxonomy)
        summary = importer.import_file(args.input)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_seed_rules(args: argparse.Namespace) -> None:
    with session() as connection:
        summary = RuleTemplateSeeder(connection).seed_file(args.input)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_list_candidates(args: argparse.Namespace) -> None:
    with session() as connection:
        rows = RelationCandidateRepository(connection).list(
            status=args.status,
            source=args.source,
            relation_type=args.relation_type,
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_accept_candidate(args: argparse.Namespace) -> None:
    with session() as connection:
        relation_id = RelationCandidateRepository(connection).accept(args.candidate_id)
    print(json.dumps({"candidate_id": args.candidate_id, "relation_id": relation_id}, ensure_ascii=False, indent=2))


def cmd_reject_candidate(args: argparse.Namespace) -> None:
    with session() as connection:
        RelationCandidateRepository(connection).reject(args.candidate_id)
    print(json.dumps({"candidate_id": args.candidate_id, "status": "rejected"}, ensure_ascii=False, indent=2))


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

    seed_tax = subparsers.add_parser("seed-taxonomy", help="Seed object_class from taxonomy JSON.")
    seed_tax.set_defaults(func=cmd_seed_taxonomy)

    seed_demo = subparsers.add_parser("seed-demo", help="Insert demo drawing, objects, and rules.")
    seed_demo.set_defaults(func=cmd_seed_demo)

    import_json = subparsers.add_parser("import-json", help="Import normalized CAD parser JSON.")
    import_json.add_argument("--input", required=True, help="Path to normalized JSON file.")
    import_json.add_argument(
        "--strict-taxonomy",
        action="store_true",
        help="Reject objects whose class_name is not in object_class.",
    )
    import_json.set_defaults(func=cmd_import_json)

    seed_rules_parser = subparsers.add_parser("seed-rules", help="Seed rule_template from rule JSON.")
    seed_rules_parser.add_argument("--input", required=True, help="Path to rule JSON file.")
    seed_rules_parser.set_defaults(func=cmd_seed_rules)

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

    candidates = subparsers.add_parser("list-candidates", help="List relation candidates.")
    candidates.add_argument("--status", choices=["pending", "accepted", "rejected", "superseded"])
    candidates.add_argument("--source", choices=["rule", "llm", "parser", "import"])
    candidates.add_argument("--relation-type")
    candidates.set_defaults(func=cmd_list_candidates)

    accept_candidate = subparsers.add_parser("accept-candidate", help="Accept a relation candidate.")
    accept_candidate.add_argument("candidate_id")
    accept_candidate.set_defaults(func=cmd_accept_candidate)

    reject_candidate = subparsers.add_parser("reject-candidate", help="Reject a relation candidate.")
    reject_candidate.add_argument("candidate_id")
    reject_candidate.set_defaults(func=cmd_reject_candidate)

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
