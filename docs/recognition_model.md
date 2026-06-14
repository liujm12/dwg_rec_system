# Recognition Model

This document describes the planned recognition modeling layer for CAD/DWG/DXF/PDF/image sources.

The current repository already stores accepted objects, attributes, geometry, relations, quantities, and audit records. The next major risk is recognition accuracy: if detected objects are wrong, downstream quantity, budget, installation guidance, and workflow planning will also be wrong.

The recognition layer should make uncertainty explicit instead of pretending every parser or model output is final truth.

## Why This Layer Matters

DWG/DXF sources may preserve useful CAD semantics:

- block names
- handles
- layers
- line types
- entity types
- coordinates

PDF CAD drawings usually lose much of that structure. They often preserve only:

- vector paths
- lines and curves
- text
- images
- colors
- page coordinates

For PDF, the system must infer engineering objects from visual and spatial evidence. That requires a model of primitives, candidates, hypotheses, confidence, and review.

## Target Flow

```text
PDF/DWG/DXF/image source
  -> source_document
  -> drawing_page
  -> drawing_primitive
  -> recognition_candidate
  -> object_hypothesis
  -> accepted hypothesis
  -> normalized JSON / ObjectInput
  -> ObjectStore
  -> cad_object + geometry + cad_meta + attribute
```

The accepted object path should remain:

```text
accepted hypothesis -> ObjectStore.create_object()
```

Recognition code should not bypass `ObjectStore`.

## Concepts

### Source Document

Represents the original input file.

Future fields may include:

```text
id
project_id
file_path
file_type
source_hash
page_count
parser_name
parser_version
created_at
```

### Drawing Page

Represents a PDF page, CAD layout, or sheet coordinate system.

Future fields may include:

```text
id
source_document_id
page_no
width
height
unit
scale
rotation
created_at
```

### Drawing Primitive

Represents low-level extracted elements.

Examples:

```text
line
polyline
rect
circle
arc
path
text
image
symbol_fragment
```

Future fields may include:

```text
id
page_id
primitive_type
layer
stroke_color
fill_color
line_width
bbox_json
geometry_json
text
font_name
font_size
raw_json
```

### Recognition Candidate

Represents a model, rule, OCR, or parser suggestion.

Examples:

```text
possible VALVE, confidence 0.72
possible FLOW_METER, confidence 0.18
possible TEXT_LABEL, confidence 0.91
```

Future fields may include:

```text
id
page_id
candidate_type
class_code
bbox_json
confidence
source
model_name
model_version
evidence_json
status
created_at
```

### Candidate Primitive Link

Connects a recognition candidate to the primitives that support it.

Future fields may include:

```text
candidate_id
primitive_id
role
```

Example roles:

```text
symbol_geometry
nearby_label
leader_line
dimension_text
connection_line
```

### Object Hypothesis

Represents a combined engineering object guess.

Example:

```text
symbol candidate + nearby text V-101 + nearby DN100 + pipe overlap
  -> VALVE hypothesis
```

Future fields may include:

```text
id
page_id
class_code
bbox_json
geometry_json
attributes_json
confidence
evidence_json
status
created_at
```

Suggested statuses:

```text
pending
accepted
rejected
merged
superseded
```

### Hypothesis To Object

When a hypothesis is accepted, it may become a `cad_object`.

Future fields may include:

```text
hypothesis_id
object_id
```

This preserves the chain:

```text
cad_object -> object_hypothesis -> recognition_candidate -> drawing_primitive -> source_document
```

## Evidence Fusion

Recognition accuracy should improve by combining multiple signals.

Example for `VALVE`:

```text
symbol shape resembles valve          + shape score
located on pipe centerline            + spatial score
near text V-101                       + tag evidence
near text DN100                       + attribute evidence
source layer or color suggests piping + CAD/PDF evidence
```

No single signal should be treated as perfect.

Good recognition pipelines should combine:

- geometric rules
- CAD metadata
- vector primitive grouping
- OCR/text extraction
- symbol libraries
- object detection models
- relation inference
- human feedback

## Acceptance Boundary

Recognition candidates are not final objects.

Correct flow:

```text
recognition candidate
  -> object hypothesis
  -> acceptance / review
  -> ObjectStore
```

Incorrect flow:

```text
model output
  -> direct cad_object write
```

Acceptance may be automatic when confidence and deterministic evidence are strong. Low-confidence or conflicting hypotheses should remain pending for review.

## PDF-Specific Identity

PDF objects do not have CAD handles.

Before entering `ObjectStore`, the recognition layer should generate deterministic source-local ids using stable data such as:

- source document hash
- page number
- normalized bbox
- class code
- primitive ids or geometry hash

The resulting id should populate the normalized JSON `handle` field so repeated imports update the same object instead of creating duplicates.

## Downstream Impact

Quantity, budget, and installation outputs should not assume recognition is perfect.

They should preserve:

- source object ids
- confidence
- status
- evidence
- generator version
- profile version

When input data is missing or uncertain, downstream services should produce reviewable records instead of pretending the result is exact.

Example:

```text
DUCT missing width/height
  -> quantity_item quantity_method = manual_review
  -> evidence_json explains missing geometry
```

## Implementation Timing

Do not add the full recognition schema immediately.

Recommended sequence:

```text
1. Finish quantity takeoff with evidence and manual review.
2. Add data quality checks for missing attributes, geometry, and relations.
3. Design recognition tables before real PDF/DWG parser implementation.
4. Implement PDF/DWG primitive extraction and candidate generation.
5. Connect accepted hypotheses to ObjectStore.
```

The recognition layer should be introduced through its own architecture task because it will add several tables and service boundaries.

