# Agent Tasks Round 11

Round 11 strengthens deterministic relation inference after the parser adapter boundary is in place.

Round 10 provided:

```text
parser adapter input
  -> normalized recognition payload
  -> RecognitionImportService
  -> source_document + drawing_page + drawing_primitive
  -> recognition_candidate + object_hypothesis
```

Round 11 should improve this layer:

```text
cad_object + geometry + attributes + text/labels
  -> deterministic spatial and semantic rule strategies
  -> relation_candidate with evidence
  -> optional review
  -> accepted relation
```

## Round Goal

Implement stronger rule inference while preserving the existing review boundary.

The output of Round 11 is not a new parser, OCR engine, CV model, LLM classifier, API, UI, scheduler, budget engine, or automatic design optimizer. It is a more capable deterministic relation inference layer that can create better `relation_candidate` rows for later review, acceptance, budgeting, installation guidance, and workflow planning.

Round 11 should answer questions like:

```text
Can the system infer containment from bounding boxes?
Can the system infer overlap-based spatial relations?
Can nearby text labels be associated with objects?
Can class-compatible relation templates constrain noisy spatial matches?
Can every inferred relation explain why it was created?
Can stronger inference improve downstream workflows without auto-mutating final truth?
```

## Coordination Rules

- Every agent must read `CLAUDE.md`, `docs/architecture.md`, `docs/final_roadmap.md`, `docs/development_plan.md`, `docs/taxonomy_profile.md`, `docs/agent_tasks_round_10.md`, and this file.
- Every agent must run `python -m pytest -q`.
- Do not add OCR, CV, LLM, API, UI, web services, external parser dependencies, or optimization engines.
- Do not bypass `relation_candidate`.
- Do not write inferred relations directly to `relation` unless using the existing explicit acceptance path.
- Do not mutate `cad_object`, `quantity_item`, `budget_item`, `install_task`, `workflow_plan`, or recognition tables from the inference step.
- Keep all new inference evidence auditable and deterministic.
- Keep relation strategy behavior testable with small sample fixtures.

## Design Boundary

Round 11 should extend the relation inference layer, not the object store.

Recommended modules:

```text
dwg_rec_system/services/relation_engine.py
dwg_rec_system/spatial.py
dwg_rec_system/rules/
```

Only add a new module if it reduces real complexity. Prefer extending existing service patterns if the current code can stay readable.

The inference boundary should remain:

```text
objects + geometry + attributes + rules
  -> relation candidates
  -> candidate review
  -> accepted relations
```

## Candidate Relation Types

Round 11 should focus on deterministic relation types that improve recognition quality and downstream installation logic.

Recommended relation types:

```text
contains
located_in
labels
installed_in
installed_on
overlaps
near
connected_to
located_on_axis
```

Do not implement every type if doing so would make the round too broad. Prefer a small set with strong tests over many shallow relation names.

Minimum recommended scope:

- `contains`
- `located_in`
- `labels`
- `overlaps`

## Strategy Requirements

### Bounding Box Containment

Infer containment when one object's bbox substantially contains another object's bbox.

Recommended evidence fields:

```json
{
  "strategy": "bbox_containment",
  "container_bbox": {},
  "contained_bbox": {},
  "containment_ratio": 0.98,
  "threshold": 0.9
}
```

Recommended behavior:

- Skip objects without usable geometry or bbox.
- Use deterministic thresholds.
- Avoid creating self-relations.
- Avoid duplicate candidates for the same object pair, relation type, and rule.
- Use class compatibility where available.

### Bounding Box Overlap

Infer overlap when two bboxes intersect with enough area.

Recommended evidence fields:

```json
{
  "strategy": "bbox_overlap",
  "source_bbox": {},
  "target_bbox": {},
  "overlap_area": 1200.0,
  "source_overlap_ratio": 0.75,
  "target_overlap_ratio": 0.42,
  "threshold": 0.5
}
```

Recommended behavior:

- Handle zero-area or invalid bboxes safely.
- Keep overlap confidence lower than exact CAD-handle or explicit metadata relations.
- Use relation type `overlaps` unless a class-compatible template maps it to a stronger relation.

### Text Label Binding

Infer label relations when text-like objects or attributes are close to a target object.

Recommended evidence fields:

```json
{
  "strategy": "text_label_binding",
  "label_text": "CP-01",
  "distance": 12.5,
  "max_distance": 50.0,
  "text_bbox": {},
  "target_bbox": {}
}
```

Recommended behavior:

- Prefer explicit text objects if they exist.
- If no text object class exists yet, use objects with text/tag/name attributes where appropriate.
- Do not overwrite target object attributes in Round 11.
- Create `labels` candidates only; attribute enrichment can be a future review/correction step.

### Class-Compatible Templates

Spatial relations should be constrained by engineering class compatibility when possible.

Examples:

```text
ROOM contains CONTROL_PANEL
CABINET contains DDC
TEXT_LABEL labels CONTROL_PANEL
CONTROL_PANEL installed_on WALL
VALVE connected_to PIPE
```

Recommended behavior:

- Add rule templates or strategy config in JSON only if needed.
- Prefer existing rule template mechanisms if they already fit.
- Record the template or class compatibility reason in candidate evidence.
- If class compatibility is unknown, create lower-confidence candidates or skip based on strategy.

## Confidence Guidelines

Round 11 should keep confidence deterministic and explainable.

Suggested confidence ranges:

```text
0.85 - 0.95: strong containment with compatible classes
0.70 - 0.85: strong overlap or near label with compatible classes
0.50 - 0.70: weak overlap, generic proximity, or unknown class compatibility
```

Do not tune confidence with hidden heuristics. Put the inputs and thresholds in evidence.

## Idempotency And Duplicates

Repeated inference should not create duplicate candidates.

Round 11 should define stable candidate identity using fields such as:

```text
source_object_id
target_object_id
relation_type
rule_id or strategy_name
```

If the current schema does not enforce a unique constraint for this exact shape, service-level de-duplication is acceptable for Round 11.

## Agent A: Spatial Geometry Helpers

### Objective

Add or improve bbox helper functions needed by stronger relation inference.

### Allowed Files

- `dwg_rec_system/spatial.py`
- `dwg_rec_system/services/relation_engine.py`
- `tests/`
- `docs/`

### Disallowed Changes

- Do not add GIS dependencies.
- Do not change database geometry storage format.
- Do not require PostGIS.

### Required Behavior

Add helpers for:

- bbox validation
- bbox area
- bbox intersection
- bbox containment ratio
- bbox overlap ratios
- bbox center distance if not already available

### Required Tests

Add tests for:

- valid and invalid bboxes
- zero-area bboxes
- full containment
- partial overlap
- no overlap
- deterministic floating-point behavior

## Agent B: Containment And Overlap Inference

### Objective

Extend relation inference to create `contains`, `located_in`, and `overlaps` candidates from object geometry.

### Allowed Files

- `dwg_rec_system/services/relation_engine.py`
- `dwg_rec_system/spatial.py`
- `tests/`
- `samples/`
- `docs/`

### Disallowed Changes

- Do not accept relation candidates automatically unless existing rule behavior explicitly does so and tests cover it.
- Do not write directly to `relation`.
- Do not change quantity, budget, installation, or workflow services.

### Required Behavior

The inference strategy should:

- read active objects and their geometry
- compute containment and overlap
- create relation candidates with deterministic evidence
- skip invalid geometry safely
- avoid self-relations
- avoid duplicate candidates on repeated runs

### Required Tests

Add tests for:

- container object creates `contains` candidate
- contained object can create `located_in` candidate if strategy is enabled
- overlapping objects create `overlaps` candidate
- invalid geometry is skipped without failing the whole run
- repeated inference is idempotent
- evidence includes strategy, thresholds, and computed ratios

## Agent C: Text Label Binding

### Objective

Infer `labels` candidates between text-like objects and engineering objects.

### Allowed Files

- `dwg_rec_system/services/relation_engine.py`
- `dwg_rec_system/spatial.py`
- `dwg_rec_system/taxonomy/`
- `tests/`
- `samples/`
- `docs/`

### Disallowed Changes

- Do not overwrite object attributes.
- Do not auto-rename objects.
- Do not call OCR, CV, LLM, or parser services.

### Required Behavior

The strategy should:

- identify label sources deterministically
- match labels to nearby target objects
- prefer nearest compatible target
- create `labels` candidates with distance and text evidence
- skip ambiguous matches when confidence would be too low

### Required Tests

Add tests for:

- nearby text creates `labels` candidate
- nearest target wins when multiple targets are present
- far text is skipped
- missing text is skipped
- evidence preserves label text and distance

## Agent D: Rule Template And Class Compatibility

### Objective

Make stronger inference respect engineering class compatibility.

### Allowed Files

- `dwg_rec_system/services/relation_engine.py`
- `dwg_rec_system/rules/`
- `dwg_rec_system/taxonomy/`
- `samples/`
- `tests/`
- `docs/`

### Disallowed Changes

- Do not make taxonomy seeding dependent on Round 11 inference.
- Do not hard-code all future engineering knowledge into Python if an existing JSON rule/template mechanism can express it.

### Required Behavior

Add or reuse rule template support for:

- allowed source class
- allowed target class
- relation type
- strategy name
- minimum confidence or threshold

Candidate evidence should include the matched template or the reason compatibility was considered unknown.

### Required Tests

Add tests for:

- compatible classes produce higher-confidence candidates
- incompatible classes are skipped or downgraded consistently
- missing compatibility data does not crash inference
- templates remain deterministic across repeated seeding/import

## Agent E: Documentation And Acceptance

### Objective

Document stronger relation inference and update project docs after implementation lands.

### Required Documentation

Update docs to explain:

- Round 11 adds stronger deterministic inference, not AI recognition
- new relation types and strategy boundaries
- relation candidates remain reviewable before final acceptance
- confidence and evidence must be auditable
- downstream modules should consume accepted relations only unless explicitly designed otherwise

After implementation lands:

- mark Milestone 11 as complete
- set the next milestone based on project priority:
  - review and correction workflow, or
  - real DXF/PDF parser adapter, or
  - API/UI

## Final Round 11 Acceptance

Round 11 is complete when this works from a clean temporary database:

```powershell
python -m pytest -q
$env:DWG_REC_DB="data/round11_acceptance.db"
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy
python -m dwg_rec_system.cli import-json --input samples/demo_round11_relations.json --strict-taxonomy
python -m dwg_rec_system.cli seed-rules --input samples/demo_round11_rules.json
python -m dwg_rec_system.cli infer-relations
python -m dwg_rec_system.cli list-candidates
```

Expected:

- tests pass
- containment, overlap, and label candidates are created where sample geometry supports them
- invalid or missing geometry does not fail the full inference run
- repeated `infer-relations` does not duplicate candidates
- candidates include evidence with strategy names, thresholds, and computed measurements
- final `relation` rows are created only through the existing explicit acceptance path or existing tested auto-accept behavior
- no OCR/CV/LLM/parser/API/UI dependencies are added
