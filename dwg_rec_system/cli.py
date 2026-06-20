from __future__ import annotations

import argparse
import json
from pathlib import Path

from .db import database_path, init_database, session
from .models import CadMetaInput, GeometryInput, ObjectInput, RuleTemplateInput
from .repositories import (
    BudgetItemRepository,
    CostItemRepository,
    DrawingRepository,
    InstallDependencyRepository,
    InstallInstructionRepository,
    InstallTaskRepository,
    ObjectClassRepository,
    ProjectRepository,
    QuantityRepository,
    RelationCandidateRepository,
    RelationRepository,
    seed_rules,
)
from .importers.normalized_json import NormalizedJsonImporter
from .services.budget import BudgetGenerator
from .services.cost_items import CostItemSeeder
from .services.data_quality import DataQualityChecker, filter_findings
from .services.exports import CsvExporter
from .services.installation import (
    InstallDependencyGenerator,
    InstallInstructionGenerator,
    InstallTaskGenerator,
)
from .services.object_store import ObjectStore
from .services.quantity import QuantityGenerator
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


def cmd_generate_quantities(args: argparse.Namespace) -> None:
    with session() as connection:
        summary = QuantityGenerator(connection).generate(
            project_id=args.project_id,
            drawing_id=args.drawing_id,
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_list_quantities(args: argparse.Namespace) -> None:
    with session() as connection:
        rows = QuantityRepository(connection).list(
            project_id=args.project_id,
            drawing_id=args.drawing_id,
            class_code=args.class_code,
            status=args.status,
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_export_quantities_csv(args: argparse.Namespace) -> None:
    with session() as connection:
        output = CsvExporter(connection).export_quantities(
            args.output,
            project_id=args.project_id,
            drawing_id=args.drawing_id,
            class_code=args.class_code,
            status=args.status,
        )
    print(f"exported: {output}")


def _quality_result(args: argparse.Namespace) -> dict:
    with session() as connection:
        return DataQualityChecker(
            connection,
            low_confidence_threshold=args.low_confidence_threshold,
        ).check(
            project_id=args.project_id,
            drawing_id=args.drawing_id,
        )


def cmd_check_data_quality(args: argparse.Namespace) -> None:
    result = _quality_result(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_list_quality_findings(args: argparse.Namespace) -> None:
    result = _quality_result(args)
    findings = filter_findings(
        result["findings"],
        severity=args.severity,
        category=args.category,
    )
    print(json.dumps(findings, ensure_ascii=False, indent=2))


def cmd_export_quality_findings_csv(args: argparse.Namespace) -> None:
    result = _quality_result(args)
    findings = filter_findings(
        result["findings"],
        severity=args.severity,
        category=args.category,
    )
    with session() as connection:
        output = CsvExporter(connection).export_quality_findings(args.output, findings)
    print(f"exported: {output}")


def cmd_seed_cost_items(args: argparse.Namespace) -> None:
    with session() as connection:
        summary = CostItemSeeder(connection).seed_file(args.input)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_list_cost_items(args: argparse.Namespace) -> None:
    with session() as connection:
        rows = CostItemRepository(connection).list(
            class_code=args.class_code,
            discipline=args.discipline,
            unit=args.unit,
            status=args.status,
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_generate_budget(args: argparse.Namespace) -> None:
    with session() as connection:
        summary = BudgetGenerator(connection).generate(
            project_id=args.project_id,
            drawing_id=args.drawing_id,
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_list_budget_items(args: argparse.Namespace) -> None:
    with session() as connection:
        rows = BudgetItemRepository(connection).list(
            project_id=args.project_id,
            drawing_id=args.drawing_id,
            class_code=args.class_code,
            status=args.status,
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_export_budget_csv(args: argparse.Namespace) -> None:
    with session() as connection:
        output = CsvExporter(connection).export_budget(
            args.output,
            project_id=args.project_id,
            drawing_id=args.drawing_id,
            status=args.status,
        )
    print(f"exported: {output}")


def cmd_generate_install_tasks(args: argparse.Namespace) -> None:
    with session() as connection:
        summary = InstallTaskGenerator(
            connection,
            low_confidence_threshold=args.low_confidence_threshold,
        ).generate_tasks(
            project_id=args.project_id,
            drawing_id=args.drawing_id,
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_generate_install_dependencies(args: argparse.Namespace) -> None:
    with session() as connection:
        summary = InstallDependencyGenerator(connection).generate_dependencies(
            project_id=args.project_id,
            drawing_id=args.drawing_id,
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_generate_install_instructions(args: argparse.Namespace) -> None:
    with session() as connection:
        summary = InstallInstructionGenerator(connection).generate_instructions(
            project_id=args.project_id,
            drawing_id=args.drawing_id,
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_list_install_tasks(args: argparse.Namespace) -> None:
    with session() as connection:
        rows = InstallTaskRepository(connection).list(
            project_id=args.project_id,
            drawing_id=args.drawing_id,
            class_code=args.class_code,
            status=args.status,
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_list_install_dependencies(args: argparse.Namespace) -> None:
    with session() as connection:
        rows = InstallDependencyRepository(connection).list(
            project_id=args.project_id,
            drawing_id=args.drawing_id,
            status=args.status,
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_list_install_instructions(args: argparse.Namespace) -> None:
    with session() as connection:
        rows = InstallInstructionRepository(connection).list(
            task_id=args.task_id,
            project_id=args.project_id,
            drawing_id=args.drawing_id,
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_export_install_tasks_csv(args: argparse.Namespace) -> None:
    with session() as connection:
        output = CsvExporter(connection).export_install_tasks(
            args.output,
            project_id=args.project_id,
            drawing_id=args.drawing_id,
            class_code=args.class_code,
            status=args.status,
        )
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

    generate_quantities = subparsers.add_parser(
        "generate-quantities",
        help="Generate durable quantity_item rows from recognized objects.",
    )
    generate_quantities.add_argument("--project-id")
    generate_quantities.add_argument("--drawing-id")
    generate_quantities.set_defaults(func=cmd_generate_quantities)

    list_quantities = subparsers.add_parser("list-quantities", help="List generated quantity rows.")
    list_quantities.add_argument("--project-id")
    list_quantities.add_argument("--drawing-id")
    list_quantities.add_argument("--class-code")
    list_quantities.add_argument("--status", choices=["auto", "reviewed", "corrected", "rejected"])
    list_quantities.set_defaults(func=cmd_list_quantities)

    export_quantities = subparsers.add_parser(
        "export-quantities-csv",
        help="Export quantity rows as CSV.",
    )
    export_quantities.add_argument("--output", default=str(Path("exports/quantities.csv")))
    export_quantities.add_argument("--project-id")
    export_quantities.add_argument("--drawing-id")
    export_quantities.add_argument("--class-code")
    export_quantities.add_argument("--status", choices=["auto", "reviewed", "corrected", "rejected"])
    export_quantities.set_defaults(func=cmd_export_quantities_csv)

    check_quality = subparsers.add_parser(
        "check-data-quality",
        help="Check objects and quantities for reviewable data quality findings.",
    )
    check_quality.add_argument("--project-id")
    check_quality.add_argument("--drawing-id")
    check_quality.add_argument("--low-confidence-threshold", type=float, default=0.8)
    check_quality.set_defaults(func=cmd_check_data_quality)

    list_quality = subparsers.add_parser(
        "list-quality-findings",
        help="List recomputed data quality findings.",
    )
    list_quality.add_argument("--project-id")
    list_quality.add_argument("--drawing-id")
    list_quality.add_argument("--low-confidence-threshold", type=float, default=0.8)
    list_quality.add_argument("--severity", choices=["error", "warning", "info"])
    list_quality.add_argument(
        "--category",
        choices=[
            "missing_attribute",
            "missing_geometry",
            "low_confidence",
            "manual_review_quantity",
            "missing_relation",
            "missing_profile",
        ],
    )
    list_quality.set_defaults(func=cmd_list_quality_findings)

    export_quality = subparsers.add_parser(
        "export-quality-findings-csv",
        help="Export recomputed data quality findings as CSV.",
    )
    export_quality.add_argument("--output", default=str(Path("exports/quality_findings.csv")))
    export_quality.add_argument("--project-id")
    export_quality.add_argument("--drawing-id")
    export_quality.add_argument("--low-confidence-threshold", type=float, default=0.8)
    export_quality.add_argument("--severity", choices=["error", "warning", "info"])
    export_quality.add_argument(
        "--category",
        choices=[
            "missing_attribute",
            "missing_geometry",
            "low_confidence",
            "manual_review_quantity",
            "missing_relation",
            "missing_profile",
        ],
    )
    export_quality.set_defaults(func=cmd_export_quality_findings_csv)

    seed_cost_items = subparsers.add_parser(
        "seed-cost-items",
        help="Seed cost_item rows from JSON.",
    )
    seed_cost_items.add_argument("--input", required=True, help="Path to cost item JSON file.")
    seed_cost_items.set_defaults(func=cmd_seed_cost_items)

    list_cost_items = subparsers.add_parser("list-cost-items", help="List cost library items.")
    list_cost_items.add_argument("--class-code")
    list_cost_items.add_argument("--discipline")
    list_cost_items.add_argument("--unit")
    list_cost_items.add_argument("--status", choices=["active", "inactive"])
    list_cost_items.set_defaults(func=cmd_list_cost_items)

    generate_budget = subparsers.add_parser(
        "generate-budget",
        help="Generate budget_item rows from quantity_item and cost_item.",
    )
    generate_budget.add_argument("--project-id")
    generate_budget.add_argument("--drawing-id")
    generate_budget.set_defaults(func=cmd_generate_budget)

    list_budget = subparsers.add_parser("list-budget-items", help="List generated budget rows.")
    list_budget.add_argument("--project-id")
    list_budget.add_argument("--drawing-id")
    list_budget.add_argument("--class-code")
    list_budget.add_argument(
        "--status",
        choices=["auto", "review", "matched", "unmatched", "corrected", "rejected"],
    )
    list_budget.set_defaults(func=cmd_list_budget_items)

    export_budget = subparsers.add_parser("export-budget-csv", help="Export budget rows as CSV.")
    export_budget.add_argument("--output", default=str(Path("exports/budget.csv")))
    export_budget.add_argument("--project-id")
    export_budget.add_argument("--drawing-id")
    export_budget.add_argument(
        "--status",
        choices=["auto", "review", "matched", "unmatched", "corrected", "rejected"],
    )
    export_budget.set_defaults(func=cmd_export_budget_csv)

    generate_install_tasks = subparsers.add_parser(
        "generate-install-tasks",
        help="Generate install_task rows from recognized objects and engineering profiles.",
    )
    generate_install_tasks.add_argument("--project-id")
    generate_install_tasks.add_argument("--drawing-id")
    generate_install_tasks.add_argument("--low-confidence-threshold", type=float, default=0.8)
    generate_install_tasks.set_defaults(func=cmd_generate_install_tasks)

    generate_install_dependencies = subparsers.add_parser(
        "generate-install-dependencies",
        help="Generate simple install_dependency rows from accepted relations.",
    )
    generate_install_dependencies.add_argument("--project-id")
    generate_install_dependencies.add_argument("--drawing-id")
    generate_install_dependencies.set_defaults(func=cmd_generate_install_dependencies)

    generate_install_instructions = subparsers.add_parser(
        "generate-install-instructions",
        help="Generate deterministic install_instruction rows from tasks and dependencies.",
    )
    generate_install_instructions.add_argument("--project-id")
    generate_install_instructions.add_argument("--drawing-id")
    generate_install_instructions.set_defaults(func=cmd_generate_install_instructions)

    list_install_tasks = subparsers.add_parser("list-install-tasks", help="List install tasks.")
    list_install_tasks.add_argument("--project-id")
    list_install_tasks.add_argument("--drawing-id")
    list_install_tasks.add_argument("--class-code")
    list_install_tasks.add_argument(
        "--status",
        choices=["auto", "review", "ready", "blocked", "corrected", "rejected", "done"],
    )
    list_install_tasks.set_defaults(func=cmd_list_install_tasks)

    list_install_dependencies = subparsers.add_parser(
        "list-install-dependencies",
        help="List install dependencies.",
    )
    list_install_dependencies.add_argument("--project-id")
    list_install_dependencies.add_argument("--drawing-id")
    list_install_dependencies.add_argument(
        "--status",
        choices=["auto", "review", "corrected", "rejected"],
    )
    list_install_dependencies.set_defaults(func=cmd_list_install_dependencies)

    list_install_instructions = subparsers.add_parser(
        "list-install-instructions",
        help="List generated install instructions.",
    )
    list_install_instructions.add_argument("--task-id")
    list_install_instructions.add_argument("--project-id")
    list_install_instructions.add_argument("--drawing-id")
    list_install_instructions.set_defaults(func=cmd_list_install_instructions)

    export_install_tasks = subparsers.add_parser(
        "export-install-tasks-csv",
        help="Export install tasks as CSV.",
    )
    export_install_tasks.add_argument("--output", default=str(Path("exports/install_tasks.csv")))
    export_install_tasks.add_argument("--project-id")
    export_install_tasks.add_argument("--drawing-id")
    export_install_tasks.add_argument("--class-code")
    export_install_tasks.add_argument(
        "--status",
        choices=["auto", "review", "ready", "blocked", "corrected", "rejected", "done"],
    )
    export_install_tasks.set_defaults(func=cmd_export_install_tasks_csv)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.db:
        print(f"using environment/default database: {database_path()}")
    args.func(args)


if __name__ == "__main__":
    main()
