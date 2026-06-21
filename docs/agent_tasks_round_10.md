# Agent Tasks Round 10

Round 10 defines and implements the first parser adapter boundary on top of the Round 9 recognition modeling layer.

Round 9 provided:

```text
source document
  -> drawing page
  -> drawing primitive
  -> recognition candidate
  -> object hypothesis
  -> accepted hypothesis
  -> ObjectStore
```

Round 10 should make this work:

```text
parser adapter input
  -> normalized recognition payload
  -> RecognitionImportService
  -> source_document + drawing_page + drawing_primitive
  -> recognition_candidate + object_hypothesis
```

## Round Goal

Implement the parser adapter boundary without adding heavy real parser dependencies.

The output of Round 10 is not a full PDF parser, DWG parser, OCR engine, CV detector, LLM classifier, API, UI, or production parser runtime. It is a stable adapter contract and a lightweight sample adapter that proves future parser outputs can be normalized into the Round 9 recognition payload shape.

Round 10 should answer questions like:

```text
What shape must a parser adapter output?
How are parser pages/layouts mapped to drawing_page?
How are parser primitives mapped to drawing_primitive?
How are source-local ids made deterministic?
Can a parser-like sample payload flow into recognition records?
Can adapter errors be reported without partially accepting final objects?
```

## Coordination Rules

- Every agent must read `CLAUDE.md`, `docs/architecture.md`, `docs/final_roadmap.md`, `docs/development_plan.md`, `docs/taxonomy_profile.md`, `docs/agent_tasks_round_9.md`, and this file.
- Every agent must run `python -m pytest -q`.
- Do not add heavy parser dependencies in Round 10.
- Do not implement real DWG parsing.
- Do not implement real PDF vector extraction unless it can be done with already available standard-library/sample JSON logic.
- Do not add OCR, CV, LLM, API, UI, web services, or external dependencies.
- Do not bypass `RecognitionImportService`.
- Do not write parser output directly to `cad_object`.
- Do not auto-accept hypotheses into `cad_object`.
- Keep parser-specific raw payload in JSON fields, not parser-specific tables.

## Design Boundary

Round 10 should introduce a parser adapter layer that converts parser-like source data into the Round 9 recognition payload:

```text
{
  "source_document": {},
  "pages": [
    {
      "page": {},
      "primitives": [],
      "candidates": [],
      "hypotheses": []
    }
  ]
}
```

Recommended module location:

```text
dwg_rec_system/parsers/
  __init__.py
  base.py
  sample_json.py
```

Do not put parser normalization logic in `ObjectStore`, `RecognitionImportService`, or CLI command handlers.

## Adapter Contract

Define a small parser adapter interface.

Suggested API:

```python
class ParserAdapter:
    parser_name: str
    parser_version: str
    source_type: str

    def parse_file(self, path: str | Path) -> dict: ...
    def parse_data(self, payload: dict, source_uri: str | None = None) -> dict: ...
```

The adapter output must be a valid recognition payload consumable by `RecognitionImportService`.

The adapter should not:

- call `ObjectStore`
- create `cad_object`
- accept hypotheses
- run relation inference
- run quantity, budget, installation, or workflow generation

## Source Identity Rules

Round 10 should document and test deterministic identity rules.

Recommended rules:

- `source_document.source_uri` should be the original input file path or stable source URI.
- `source_document.source_type` should be one of the Round 9 values: `pdf`, `dwg`, `dxf`, `image`, `cad_export`, `json`, `unknown`.
- `drawing_page.page_no` should be used for page-based sources such as PDF/image.
- `drawing_page.layout_name` should be used for CAD layout/sheet sources such as DWG/DXF.
- `drawing_primitive.source_local_id` should be deterministic within a page/layout.
- If a parser does not provide ids, generate stable ids from page/layout, primitive type, index, and rounded bbox/text where practical.
- `recognition_candidate.source_local_id` should be deterministic within a page/layout.
- `object_hypothesis.source_local_id` should be deterministic within a page/layout.

## Geometry And Coordinate Rules

Round 10 should keep geometry simple and parser-agnostic.

Recommended behavior:

- Preserve parser raw geometry in `geometry`.
- Preserve bbox as `{min_x, min_y, max_x, max_y}` when available.
- Preserve text primitives in `text`.
- Preserve style/layer/block/color data in `style` or `raw`.
- Do not assume a final coordinate origin convention.
- Store page width, height, unit, scale, and rotation when provided.

## Sample Parser JSON Contract

Round 10 should provide a small sample parser input that is not yet the Round 9 recognition payload. The sample adapter should convert it into the recognition payload.

Suggested sample file:

```text
samples/demo_parser_output.json
```

Suggested input shape:

```json
{
  "source": {
    "uri": "samples/demo_parser_output.pdf",
    "type": "pdf",
    "title": "Demo parser output"
  },
  "pages": [
    {
      "page_no": 1,
      "width": 420,
      "height": 297,
      "unit": "mm",
      "entities": [
        {
          "id": "box-cp01",
          "type": "rect",
          "bbox": {"min_x": 100, "min_y": 100, "max_x": 160, "max_y": 180},
          "text": null,
          "style": {"layer": "E-BMS"}
        }
      ],
      "detections": [
        {
          "id": "det-cp01",
          "class_code": "CONTROL_PANEL",
          "confidence": 0.91,
          "entity_ids": ["box-cp01"],
          "attributes": {"tag": "CP-01"}
        }
      ]
    }
  ]
}
```

The adapter should map:

- `source` -> `source_document`
- `pages[]` -> `drawing_page`
- `entities[]` -> `drawing_primitive`
- `detections[]` -> `recognition_candidate`
- optionally `detections[]` -> one `object_hypothesis` per detection

## Error Handling

Round 10 should report adapter errors clearly without writing partial final objects.

Recommended behavior:

- Adapter validation errors should raise `ValueError` with actionable messages.
- Missing source URI should be an error.
- Missing page list should be an error.
- Unsupported entity type should map to `unknown` unless strict mode is requested.
- Unknown detection class should still be represented as a candidate/hypothesis by default; taxonomy validation can happen later.
- CLI should print errors through normal exception behavior; tests should cover service-level errors.

## Agent A: Parser Adapter Interface And Sample Adapter

### Objective

Create the parser adapter package and a lightweight sample JSON adapter.

### Allowed Files

- `dwg_rec_system/parsers/`
- `dwg_rec_system/services/`
- `tests/`
- `samples/`
- `docs/`

### Disallowed Changes

- Do not add external parser libraries.
- Do not implement real PDF/DWG/DXF parsing.
- Do not write to `cad_object`.

### Required Behavior

Add:

```text
dwg_rec_system/parsers/__init__.py
dwg_rec_system/parsers/base.py
dwg_rec_system/parsers/sample_json.py
samples/demo_parser_output.json
```

The sample adapter should:

- read sample parser JSON
- convert it into a recognition payload
- generate deterministic source-local ids when ids are missing
- preserve raw parser entity/detection data in JSON evidence/raw fields

### Required Tests

Add tests for:

- adapter output has `source_document` and `pages`
- entities become primitives
- detections become recognition candidates
- detections become object hypotheses
- candidate primitive links are created from `entity_ids`
- missing entity ids are ignored or reported deterministically
- generated ids are stable across repeated conversion

## Agent B: Parser Import Service

### Objective

Add a service that runs a parser adapter and imports its recognition payload through `RecognitionImportService`.

### Allowed Files

- `dwg_rec_system/services/`
- `dwg_rec_system/parsers/`
- `tests/`
- `docs/`

### Disallowed Changes

- Do not bypass `RecognitionImportService`.
- Do not accept hypotheses automatically.
- Do not run downstream engineering generators.

### Required Behavior

Create or extend:

```text
dwg_rec_system/services/parser_import.py
```

Suggested API:

```python
class ParserImportService:
    def import_file(self, path: str | Path, adapter_name: str = "sample-json") -> dict: ...
```

The service should:

- select a supported adapter by name
- run the adapter
- pass the recognition payload to `RecognitionImportService`
- return a summary that includes adapter name/version and recognition import counts

### Required Tests

Add tests for:

- sample adapter import creates source/page/primitive/candidate/hypothesis rows
- unsupported adapter name raises `ValueError`
- parser import does not create `cad_object`
- repeated parser import is idempotent through Round 9 source-local ids

## Agent C: Parser CLI And Export

### Objective

Expose sample parser import through CLI.

### Required Commands

```powershell
python -m dwg_rec_system.cli import-parser-output --input samples/demo_parser_output.json --adapter sample-json
```

Optional commands:

```powershell
python -m dwg_rec_system.cli list-parser-adapters
```

### Allowed Files

- `dwg_rec_system/cli.py`
- `dwg_rec_system/parsers/`
- `dwg_rec_system/services/`
- `tests/`
- `README.md`
- `docs/`

### Disallowed Changes

- Do not add a real parser dependency.
- Do not accept hypotheses automatically.
- Do not add API/UI behavior.

### Required Behavior

`import-parser-output` should:

- run `ParserImportService`
- print JSON summary
- create recognition records only

`list-parser-adapters` should:

- print available adapter metadata as JSON

### Required Tests

Add tests for:

- CLI import prints valid JSON
- CLI import creates recognition records
- CLI import does not create final objects
- adapter listing includes `sample-json`

## Agent D: Documentation And Acceptance

### Objective

Document the parser adapter boundary and update project docs after implementation lands.

### Required Documentation

Update docs to explain:

- Round 10 adds parser adapter boundary, not real parser execution
- parser adapters output recognition payloads
- source-local ids must be deterministic
- real DXF/PDF/DWG work should use the same boundary
- no parser output writes directly to `cad_object`

After implementation lands:

- mark Milestone 10 as complete
- set the next milestone based on project priority:
  - stronger rule inference, or
  - real DXF/PDF parser adapter, or
  - review/correction workflow

## Final Round 10 Acceptance

Round 10 is complete when this works from a clean temporary database:

```powershell
python -m pytest -q
$env:DWG_REC_DB="data/round10_acceptance.db"
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli list-parser-adapters
python -m dwg_rec_system.cli import-parser-output --input samples/demo_parser_output.json --adapter sample-json
python -m dwg_rec_system.cli list-source-documents
python -m dwg_rec_system.cli list-recognition-candidates
python -m dwg_rec_system.cli list-object-hypotheses
python -m dwg_rec_system.cli list-objects
```

Expected:

- tests pass
- parser adapter list includes `sample-json`
- sample parser output imports into Round 9 recognition records
- candidates and hypotheses remain pending
- no final `cad_object` rows are created by parser import
- no real parser dependencies, OCR/CV/LLM services, API, UI, or web services are added
