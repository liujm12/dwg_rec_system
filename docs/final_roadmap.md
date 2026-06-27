# Final Roadmap

This roadmap describes the long-term direction for this repository: a multi-discipline CAD/DWG recognition data foundation that can support equipment recognition, engineering quantity takeoff, budgeting, installation guidance, and installation workflow planning.

The project should continue to use the current `Object + Relation + Context` architecture as its core. Recognition, budgeting, and installation planning should grow on top of the object store and engineering graph instead of replacing them with discipline-specific tables too early.

## 1. Product Goal

The final system should support this flow:

```text
CAD/DWG/DXF/PDF/image source
  -> parser / CAD plugin / OCR / AI recognition
  -> recognition modeling layer
  -> accepted object hypothesis
  -> normalized JSON
  -> ObjectStore
  -> cad_object + geometry + cad_meta + attribute
  -> relation_candidate
  -> accepted relation
  -> quantity_item
  -> budget_item
  -> install_task + install_dependency
  -> workflow_plan + workflow_step + workflow_issue
  -> reports, budgets, installation instructions, workflow plans
```

The target is not only to identify objects in drawings. The system should eventually understand:

- what objects exist in each drawing
- which discipline each object belongs to
- where each object is located
- how objects are connected or dependent on each other
- how quantities should be calculated
- how budget items should be matched
- how installation tasks should be generated and sequenced
- how recognition evidence supports each accepted object

## 2. Architectural Position

The repository currently owns the middle layer of the system:

```text
recognition output -> structured engineering data -> relation graph
```

It should remain parser-agnostic. DWG parsers, DXF parsers, CAD plugins, OCR services, and LLM preprocessing tools should either produce normalized JSON directly or produce recognition hypotheses that can be accepted into the same normalized import path.

The stable center should remain:

```text
cad_object
geometry
cad_meta
attribute
relation_candidate
relation
object_class
rule_template
correction_log
```

Do not let parser-specific logic, budgeting logic, or installation workflow logic bypass this core.

PDF and image recognition should not write directly to `cad_object`. It should preserve primitives, candidates, hypotheses, confidence, and evidence before accepted hypotheses enter `ObjectStore`.

## 3. Database Roadmap

### 3.1 Preserve Current Core Tables

These existing tables should remain the foundation:

```text
project
drawing
cad_object
geometry
cad_meta
attribute
object_class
rule_template
relation_candidate
relation
manual_relation
correction_log
artifact
```

Their responsibilities should stay clear:

- `cad_object`: universal recognized engineering object
- `geometry`: object position, size, bounds, and future geometry payloads
- `cad_meta`: original CAD metadata such as layer, block name, color, owner block
- `attribute`: flexible discipline-specific facts
- `object_class`: taxonomy and discipline classification
- `relation_candidate`: inferred or imported relation suggestions
- `relation`: accepted engineering graph edges
- `rule_template`: deterministic inference rules
- `correction_log`: human correction and audit trail
- `artifact`: generated files and deliverables

Avoid adding first-class tables such as `pump`, `valve`, `duct`, `panel`, or `sensor` unless there is a later architecture decision. Discipline-specific facts should usually live in `attribute`, taxonomy metadata, or upper-layer generated tables.

### 3.2 Taxonomy Expansion

The current taxonomy should evolve into a multi-discipline engineering dictionary. The first expansion can stay JSON-based to avoid locking the database design too early.

Recommended future taxonomy fields:

```json
{
  "code": "VALVE",
  "name_cn": "阀门",
  "discipline": "PLUMBING",
  "parent_code": "PIPE_ACCESSORY",
  "aliases": ["阀", "手阀", "控制阀"],
  "expected_attributes": [
    "tag",
    "diameter",
    "material",
    "pressure_rating",
    "system"
  ],
  "budget": {
    "unit": "个",
    "quantity_method": "count_by_object",
    "group_by": ["diameter", "material", "pressure_rating"]
  },
  "installation": {
    "work_package": "管道附件安装",
    "default_steps": ["定位", "安装", "连接", "试压", "标识"],
    "required_predecessors": ["PIPE_INSTALLED"]
  },
  "relations": [
    "installed_on",
    "connected_to",
    "located_in",
    "belongs_to_system"
  ]
}
```

If taxonomy JSON becomes too large or needs querying, add extension tables later:

```text
object_class_profile
class_attribute_definition
class_budget_rule
class_install_template
```

Recommended rule: start with JSON profiles, then promote stable fields into tables only after repeated use proves the shape.

### 3.3 Recognition Modeling Tables

Object recognition accuracy is a long-term core risk. Round 9 introduced the first recognition modeling layer before real PDF/DWG/DXF recognition work.

Round 9 durable tables:

```text
source_document
drawing_page
drawing_primitive
recognition_candidate
recognition_candidate_primitive
object_hypothesis
hypothesis_candidate
hypothesis_to_object
```

Responsibilities:

- preserve source file and page/layout context
- preserve low-level primitives such as lines, paths, text, circles, and images
- preserve model/rule/OCR candidates and confidence
- combine candidates into object hypotheses
- allow review, rejection, merge, and supersession before creating final objects
- map accepted hypotheses to `cad_object` through `hypothesis_to_object`

This layer is especially important for PDF CAD drawings because CAD handles, blocks, and layers may be missing or unreliable. Parser adapters should write compatible recognition payloads or records into this layer before accepted hypotheses enter `ObjectStore`.

The first parser adapter boundary is now in place. The bundled `sample-json` adapter is a representative contract adapter: it converts parser-like source output into source documents, pages, primitives, recognition candidates, and object hypotheses. It is not a real PDF/DWG/DXF parser, and it does not auto-accept hypotheses into `cad_object`.

### 3.4 Engineering Quantity Tables

Budgeting should be based on auditable quantity items, not temporary ad hoc queries.

Add `quantity_item` when quantity takeoff work begins:

```text
quantity_item
- id
- project_id
- drawing_id
- source_object_id
- class_code
- discipline
- item_name
- spec
- unit
- quantity
- quantity_method
- group_key
- location
- system_code
- confidence
- source
- evidence_json
- status
- created_at
- updated_at
```

Example quantity outputs:

```text
VALVE DN100 stainless ball valve      12 个
DUCT 800x400 galvanized duct          85.6 平方米
CABLE YJV-5x10                        120 米
PUMP 2.2kW centrifugal pump             3 台
```

The quantity service should transform:

```text
cad_object + attribute + geometry + relation -> quantity_item
```

Supported methods should start simple:

- count by object
- length by geometry
- area by geometry and attributes
- grouped count by selected attributes
- formula-based calculation from known attributes

### 3.5 Budget Tables

Budget data should stay separate from quantity data. Quantity answers "how much"; budget answers "how much money under which pricing rule".

Minimal tables:

```text
cost_item
budget_item
```

`cost_item` is the price or quota library:

```text
cost_item
- id
- code
- name
- discipline
- class_code
- spec_pattern
- unit
- unit_price_material
- unit_price_labor
- unit_price_machine
- currency
- region
- version
- effective_from
- effective_to
- description
```

`budget_item` is the project-specific result:

```text
budget_item
- id
- project_id
- drawing_id
- quantity_item_id
- cost_item_id
- discipline
- item_name
- spec
- unit
- quantity
- unit_price
- material_cost
- labor_cost
- machine_cost
- total_cost
- pricing_source
- confidence
- status
- evidence_json
- created_at
- updated_at
```

Budget flow:

```text
quantity_item
  -> match cost_item
  -> generate budget_item
  -> summarize by project / drawing / discipline / system / area
```

### 3.6 Installation Tables

Installation guidance should be generated from structured installation tasks, not only free-form text.

Round 7 durable tables:

```text
install_task
install_dependency
install_instruction
```

Class-level defaults currently remain in `engineering_class_profiles.json` under `installation.work_package`, `installation.default_steps`, and `installation.required_predecessors`. Promote them into a future `install_template` table only if repeated use proves the database shape.

`install_task` stores project-specific tasks:

```text
install_task
- id
- project_id
- drawing_id
- object_id
- class_code
- discipline
- task_name
- work_package
- location
- system_code
- priority
- estimated_duration
- crew_type
- source
- confidence
- status
- evidence_json
- created_at
- updated_at
```

`install_dependency` stores workflow constraints:

```text
install_dependency
- id
- predecessor_task_id
- successor_task_id
- dependency_type
- reason
- source
- confidence
- evidence_json
- status
```

Common dependency types:

```text
finish_to_start
start_to_start
inspection_before
pressure_test_before
power_before_commissioning
```

`install_instruction` stores generated human-readable instructions:

```text
install_instruction
- id
- task_id
- instruction_text
- generator
- generator_version
- source_json
- created_at
```

Installation flow:

```text
cad_object + relation + taxonomy installation profile
  -> install_task
  -> install_dependency
  -> install_instruction
```

Round 7 installation guidance is not a schedule optimizer. It records object-derived work, simple relation-based dependency evidence, and deterministic instruction text. Workflow graph planning and recommended sequencing belong to the next milestone.

### 3.7 Workflow Planning Tables

Workflow planning should remain separate from installation guidance. Installation tasks describe what needs to be installed; workflow plans describe a generated review sequence for a specific scope.

Round 8 durable tables:

```text
workflow_plan
workflow_step
workflow_issue
```

`workflow_plan` stores one generated planning run:

```text
workflow_plan
- id
- project_id
- drawing_id
- name
- scope_json
- generator
- generator_version
- status
- summary_json
- created_at
- updated_at
```

`workflow_step` stores deterministic ordered rows inside a plan:

```text
workflow_step
- id
- plan_id
- task_id
- sequence_no
- sequence_group
- discipline
- work_package
- location
- system_code
- dependency_count
- blocked_by_count
- status
- evidence_json
- created_at
- updated_at
```

`workflow_issue` stores planning problems for review:

```text
workflow_issue
- id
- plan_id
- task_id
- dependency_id
- severity
- category
- code
- message
- evidence_json
- status
- created_at
- updated_at
```

Workflow flow:

```text
install_task + install_dependency
  -> workflow_plan
  -> workflow_step
  -> workflow_issue
```

Round 8 workflow planning is not a Gantt chart, calendar schedule, critical-path optimizer, or crew/resource allocation system. It records a deterministic dependency-based sequence and the issues that make that sequence unsafe or review-worthy.

## 4. Module Roadmap

Recommended long-term package layout:

```text
dwg_rec_system/
  importers/
    normalized_json.py
    dxf_adapter.py
    dwg_adapter.py
    ocr_adapter.py

  recognition/
    primitives.py
    candidates.py
    hypotheses.py
    evidence.py

  services/
    object_store.py
    taxonomy.py
    spatial_index.py
    relation_engine.py
    exports.py

    rules.py
    candidates.py
    quantity.py
    budget.py
    installation.py
    workflow.py
    validation.py

  domain/
    quantity_models.py
    budget_models.py
    install_models.py

  exporters/
    csv_exporter.py
    excel_exporter.py
    budget_exporter.py
    install_plan_exporter.py

  taxonomy/
    cad_object_taxonomy.json
    engineering_class_profiles.json
```

Near-term module priority:

```text
1. services/rules.py
2. services/candidates.py
3. services/quantity.py
4. services/budget.py
5. services/installation.py
6. services/workflow.py
```

Do not add a web API until the CLI workflow is stable. The eventual API should reuse these services instead of duplicating import, inference, quantity, or budget logic.

## 5. Multi-Discipline Scope

Start with a limited but useful multi-discipline taxonomy. Recommended first batch:

```text
HVAC
PLUMBING
ELEC
BAS / ICA
CLEANROOM
```

### 5.1 HVAC

Core object classes:

```text
AHU
FFU
FAN
DUCT
AIR_DIFFUSER
DAMPER
FILTER
VAV
SENSOR_TEMP
```

Important attributes:

```text
airflow
size
material
elevation
system
pressure
power
```

Quantity methods:

- equipment by count
- duct by area or length
- diffuser and damper by count
- filters by count or set

### 5.2 Plumbing / Process Piping

Core object classes:

```text
PIPE
VALVE
PUMP
TANK
PIPE_FILTER
FLOW_METER
PRESSURE_GAUGE
DRAIN
SPRINKLER
```

Important attributes:

```text
diameter
material
pressure_rating
medium
system
length
elevation
```

Quantity methods:

- pipe by length
- valve by count grouped by diameter and material
- pump and tank by count
- instruments by count

### 5.3 Electrical

Core object classes:

```text
PANEL
DISTRIBUTION_BOX
CABLE_TRAY
CABLE
LIGHT
SWITCH
SOCKET
GROUNDING
TRANSFORMER
UPS
```

Important attributes:

```text
voltage
power
cable_type
cross_section
tray_size
phase
circuit_no
```

Quantity methods:

- panel and box by count
- cable tray by length
- cable by length
- light, switch, and socket by count

### 5.4 BAS / ICA

Core object classes:

```text
PLC
DCC
IO_MODULE
SENSOR
ACTUATOR
VALVE_ACTUATOR
CONTROL_PANEL
NETWORK_SWITCH
```

Important attributes:

```text
io_type
signal_type
point_no
protocol
panel_no
controlled_object
```

Quantity methods:

- control panel by count
- module by count
- control point by point count
- sensor and actuator by count
- communication or control cable by length

### 5.5 Cleanroom

Core object classes:

```text
CLEANROOM
ROOM
PASS_BOX
AIR_SHOWER
FFU
HEPA_FILTER
DIFFERENTIAL_PRESSURE_SENSOR
CLEAN_DOOR
```

Important attributes:

```text
cleanliness_class
room_no
area
pressure
air_change_rate
```

Quantity methods:

- room by area and cleanroom class
- cleanroom equipment by count
- filters by count
- differential pressure points by count

## 6. Relation Type Roadmap

Relations are the bridge between drawing recognition and engineering understanding. Without relations, the system can only produce flat lists. With relations, it can reason about systems, budgets, dependencies, and installation order.

Recommended standard relation types:

```text
located_in
contains
connected_to
installed_on
mounted_on
powered_by
controlled_by
serves
belongs_to_system
labels
has_tag
requires
near
crosses
conflicts_with
```

Intended usage:

- `located_in`: object is inside a room, area, drawing zone, or cleanroom
- `connected_to`: pipe, duct, cable, tray, or equipment connection
- `installed_on`: accessory installed on pipe, duct, wall, equipment, or support
- `mounted_on`: module or device mounted on a rack, cabinet, or support
- `powered_by`: equipment receives power from panel or circuit
- `controlled_by`: equipment is controlled by PLC, DCC, sensor, or controller
- `belongs_to_system`: object belongs to a process, HVAC, electrical, or cleanroom system
- `labels`: text annotation points to an object
- `conflicts_with`: detected spatial or discipline coordination conflict

All uncertain inference should write to `relation_candidate` first. Only accepted engineering truth should be stored in `relation`.

## 7. LLM Boundary

LLMs can be useful, but they should not become the system of record.

Correct LLM flow:

```text
structured object context
  -> LLM inference or explanation
  -> relation_candidate / install_instruction
  -> review or deterministic acceptance
  -> relation / install_task
```

Good LLM use cases:

- extract structured attributes from drawing text
- explain why a candidate relation is plausible
- generate human-readable installation instructions
- summarize budget differences
- suggest missing attributes or likely object classes

Avoid:

- sending raw DWG files directly to an LLM as the only source of truth
- allowing LLM output to write directly to final `relation`
- allowing LLM output to overwrite budget or correction records without audit
- bypassing `ObjectStore`, `relation_candidate`, or `correction_log`

## 8. Implementation Milestones

### M1: Normalized Import Foundation

Status: complete.

Scope:

- normalized JSON import
- object store ingestion
- taxonomy seeding
- spatial query
- baseline relation inference
- CSV export

### M2: Rule And Candidate Workflow

Status: complete.

Scope:

- `seed-rules --input samples/demo_rules.json`
- `list-candidates`
- `accept-candidate`
- `reject-candidate`
- `import-json --strict-taxonomy`
- end-to-end demo that imports objects, seeds rules, infers one relation, and exports CSV

Goal:

```text
seed-taxonomy
  -> import-json
  -> seed-rules
  -> infer-relations
  -> list/review candidates
  -> export-csv
```

### M3: Multi-Discipline Taxonomy

Status: complete.

Scope:

- rename the primary object taxonomy to `cad_object_taxonomy.json`
- create `engineering_class_profiles.json` as an overlay on existing class codes
- cover HVAC, piping, electrical, BMS, and cleanroom profile groups
- define expected attributes, relation hints, budget units, and installation hints

Suggested first target:

```text
5 disciplines
20-50 core classes per discipline
stable naming conventions
```

### M4: Quantity Takeoff

Status: complete.

Scope:

- `quantity_item`
- `services/quantity.py`
- generate quantity rows from objects, geometry, attributes, and engineering profiles
- support count, grouped count, length, area, and manual-review fallback
- export quantity CSV

### M5: Data Quality Gate

Status: complete.

Scope:

- detect missing expected attributes from `engineering_class_profiles.json`
- detect missing geometry required by quantity methods
- detect low-confidence objects and low-confidence quantity inputs
- detect missing accepted relations needed for budgeting or installation
- produce reviewable findings before budget generation

### M6: Budgeting

Status: complete.

Scope:

- `cost_item`
- `budget_item`
- `services/budget.py`
- match quantity items to cost items
- generate matched, unmatched, and reviewable budget rows
- export budget CSV

### M7: Installation Guidance

Status: complete.

Scope:

- add `install_task`, `install_dependency`, and `install_instruction`
- keep class-level installation templates in `engineering_class_profiles.json`
- generate object-level `install_task` rows from accepted objects and profiles
- generate simple relation-based `install_dependency` rows from accepted relations
- generate deterministic readable installation instructions
- export installation tasks to CSV

### M8: Workflow Planning

Status: complete.

Scope:

- add `workflow_plan`, `workflow_step`, and `workflow_issue`
- group installation tasks by discipline, work package, location, system, and dependency evidence
- produce a simple dependency graph from `install_dependency`
- topologically order tasks with deterministic tie-breaking
- detect review dependencies, review tasks, missing scope, and cycles as workflow issues
- export ordered workflow steps to CSV

### M9: Recognition Modeling Layer

Status: complete.

Scope:

- add source document, drawing page, primitive, recognition candidate, object hypothesis, and mapping tables
- preserve candidate-to-primitive and hypothesis-to-candidate evidence
- import normalized recognition JSON without creating final objects
- define acceptance flow from hypothesis to `ObjectStore`
- define deterministic source-local identity for PDF objects that lack CAD handles
- export recognition candidates and object hypotheses to CSV

Success criteria:

- recognition outputs can stay pending, accepted, rejected, merged, or superseded
- accepted hypotheses can be converted into normalized JSON or `ObjectInput`
- final objects remain traceable back to recognition evidence
- no model/parser writes directly to `cad_object` without the acceptance boundary

### M10: Parser Adapter Boundary

Status: complete.

Scope:

- add parser adapter interfaces
- add a representative parser adapter
- convert parser-like output into recognition payloads
- preserve parser metadata in recognition evidence
- keep ObjectStore unchanged

The boundary is ready for real DXF, DWG, PDF, image, OCR, or CV adapters when those parser dependencies and source samples are selected.

### M11: Stronger Rule Inference

Status: complete.

Scope:

- add containment and overlap relation strategies
- add text-to-object label binding
- add strategy selection through rule template config
- preserve relation evidence in candidates
- keep accepted relations auditable

### M12: Review And Correction Workflow

Status: next.

Scope:

- make pending relation and recognition candidates easier to review
- add correction workflow around accepted relations and object attributes
- preserve operator, reason, old value, and new value in audit records
- keep downstream budget, installation, and workflow services consuming accepted truth by default

### M13: API And UI

Scope:

- expose import, object list, object detail, candidates, relations, quantity, budget, and installation plans through API
- add review UI for candidates and corrections
- add report views for budget and installation workflow

Do not duplicate service logic in the API layer.

## 9. Near-Term Recommended Order

The most practical sequence from the current repository state is:

```text
1. Complete quantity generation and quantity CSV export.
2. Complete data quality checks for missing attributes, geometry, low confidence, and missing relations.
3. Complete cost_item, budget_item, and budget generation.
4. Complete install_task and installation guidance.
5. Complete workflow dependency planning.
6. Complete recognition modeling tables before real PDF/DWG parser work.
7. Complete parser adapter boundary.
8. Strengthen deterministic relation inference.
9. Improve review and correction workflow.
10. Connect real DWG/DXF/PDF parser adapters.
11. Add API and UI.
```

This order keeps the data foundation strong. Budgeting and installation planning depend on object identity, attributes, geometry, and relations. If those are weak, upper-layer outputs will become fragile flat reports instead of useful engineering workflows.

## 10. Design Rules To Preserve

- Keep `source_file + handle` as the object identity rule.
- Keep importers writing through `ObjectStore`.
- Keep uncertain inference writing to `relation_candidate` first.
- Keep final engineering truth in `relation`.
- Keep human correction auditable through correction tables.
- Keep parser-specific assumptions outside the object store.
- Keep recognition candidates and hypotheses separate from accepted objects.
- Preserve recognition evidence before importing uncertain PDF/DWG results into `cad_object`.
- Keep LLM output structured, reviewable, and replaceable.
- Prefer taxonomy and rule configuration over hard-coded discipline logic.
- Add new tables only when the service layer needs durable, auditable outputs.
