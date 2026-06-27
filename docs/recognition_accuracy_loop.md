# Recognition Accuracy Loop

This document defines the next project phase after Round 11: turning recognition evidence into an auditable accuracy improvement loop.

The long-term project goal is not to keep adding isolated milestones. The goal is:

```text
real CAD/PDF/DWG/DXF drawing
  -> recognized equipment, objects, text, symbols, and relations
  -> review and correction
  -> trusted objects and relations
  -> quantity, budget, installation guidance, and workflow planning
```

The current repository already has the data foundation for objects, relations, recognition evidence, parser adapters, quantities, budgets, installation guidance, and workflow planning. The next critical gap is recognition accuracy: uncertain candidates must be reviewable, corrections must be auditable, and recognition output must be measurable against annotated ground truth.

## Scope

Implement the first recognition accuracy loop:

- enhanced `relation_candidate` review
- enhanced `object_hypothesis` review
- object class, attribute, and geometry correction
- complete `correction_log` records for review and correction actions
- annotated ground-truth JSON format
- prototype evaluation report: matched, wrong, missed, precision, recall

This phase is not:

- a real PDF/DWG/DXF parser
- OCR/CV/LLM inference
- UI/API work
- production annotation tooling
- a final accuracy benchmark suite

## Review Boundary

Uncertain output should stay pending until reviewed:

```text
recognition_candidate / object_hypothesis / relation_candidate
  -> review action
  -> correction_log
  -> accepted, rejected, merged, superseded, or corrected record
```

Accepted engineering truth remains:

```text
cad_object
relation
attribute
geometry
```

Review commands must not bypass existing service boundaries:

- accepting relation candidates should still use `RelationCandidateRepository.accept`
- accepting object hypotheses should still use `HypothesisAcceptanceService`
- object corrections should update the durable object store tables and write `correction_log`

## Correction Log

Every manual review or correction should record:

```text
entity_type
entity_id
field_name
old_value
new_value
operator
reason
created_at
```

Recommended `entity_type` values:

```text
object
relation
relation_candidate
recognition_candidate
object_hypothesis
attribute
geometry
drawing
```

Examples:

- reject a relation candidate as a false positive
- accept an object hypothesis into `cad_object`
- correct a `cad_object.class`
- change attribute `tag`
- update bbox geometry

## Object Correction

Object corrections should support:

- class correction
- status correction
- attribute set/update
- bbox geometry update

Class correction should update `cad_object.class`, optionally link `class_id` when `object_class` contains the target code, and write a correction log.

Attribute correction should write through the existing `attribute` table and use `source = manual`.

Geometry correction should write through `GeometryRepository.upsert` and preserve bbox evidence through the geometry fields.

## Ground Truth Format

The first annotation format should stay small and parser-agnostic:

```json
{
  "version": "0.1",
  "source_uri": "samples/demo_parser_output.pdf",
  "objects": [
    {
      "id": "gt-cp01",
      "class_code": "CONTROL_PANEL",
      "bbox": {"min_x": 100, "min_y": 100, "max_x": 160, "max_y": 180},
      "attributes": {"tag": "CP-01"}
    }
  ],
  "relations": [
    {
      "source_id": "gt-ddc01",
      "target_id": "gt-cp01",
      "relation_type": "located_in"
    }
  ]
}
```

Round-one evaluation should focus on object hypotheses, not final accepted objects. Real parser/model work should be measured before manual acceptance changes the result.

## Evaluation Report

Prototype object evaluation should compare ground-truth objects with `object_hypothesis` rows from the same `source_uri`.

Matching rules:

- class codes must match
- bbox IoU must be greater than or equal to a configurable threshold
- one prediction can match only one ground-truth object
- unmatched predictions are false positives
- unmatched ground-truth objects are false negatives

Report fields:

```text
ground_truth
predicted
matched
false_positive
false_negative
precision
recall
by_class
matches
missed
wrong
```

This is intentionally simple. It is the first measurable loop, not the final evaluation framework.

## CLI Acceptance

Expected commands:

```powershell
python -m dwg_rec_system.cli review-candidate <candidate_id> --action accept --operator reviewer --reason "confirmed"
python -m dwg_rec_system.cli review-hypothesis <hypothesis_id> --action reject --operator reviewer --reason "wrong class"
python -m dwg_rec_system.cli correct-object-class <object_id> --class-code CONTROL_PANEL --operator reviewer --reason "manual correction"
python -m dwg_rec_system.cli set-object-attribute <object_id> --key tag --value CP-01 --operator reviewer --reason "field check"
python -m dwg_rec_system.cli correct-object-bbox <object_id> --min-x 100 --min-y 100 --max-x 160 --max-y 180 --operator reviewer --reason "bbox adjustment"
python -m dwg_rec_system.cli list-corrections
python -m dwg_rec_system.cli evaluate-recognition --ground-truth samples/demo_ground_truth.json --iou-threshold 0.5
```

Expected outcomes:

- candidate and hypothesis review actions are auditable
- accepted hypotheses still enter `cad_object` through `ObjectStore`
- object corrections update durable object records and write correction logs
- evaluation report shows matched, false positive, false negative, precision, and recall
