# Final Roadmap

This roadmap describes the long-term direction for this repository: a multi-discipline CAD/DWG recognition data foundation that can support equipment recognition, engineering quantity takeoff, budgeting, installation guidance, and installation workflow planning.

The project should continue to use the current `Object + Relation + Context` architecture as its core. Recognition, budgeting, and installation planning should grow on top of the object store and engineering graph instead of replacing them with discipline-specific tables too early.

## 1. Product Goal

The final system should support this flow:

```text
CAD/DWG/DXF/PDF/image source
  -> parser / CAD plugin / OCR / AI recognition
  -> normalized JSON
  -> ObjectStore
  -> cad_object + geometry + cad_meta + attribute
  -> relation_candidate
  -> accepted relation
  -> quantity_item
  -> budget_item
  -> install_task + install_dependency
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

## 2. Architectural Position

The repository currently owns the middle layer of the system:

```text
recognition output -> structured engineering data -> relation graph
```

It should remain parser-agnostic. DWG parsers, DXF parsers, CAD plugins, OCR services, and LLM preprocessing tools should all produce normalized JSON and then enter the same import path.

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

### 3.3 Engineering Quantity Tables

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

### 3.4 Budget Tables

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

### 3.5 Installation Tables

Installation guidance should be generated from structured installation tasks, not only free-form text.

Recommended tables:

```text
install_template
install_task
install_dependency
install_instruction
```

`install_template` stores class-level default guidance:

```text
install_template
- id
- class_code
- discipline
- template_name
- default_steps_json
- required_tools_json
- required_materials_json
- quality_check_json
- safety_notes_json
```

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
- location
- system_code
- priority
- estimated_duration
- crew_type
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
- confidence
- source
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

## 4. Module Roadmap

Recommended long-term package layout:

```text
dwg_rec_system/
  importers/
    normalized_json.py
    dxf_adapter.py
    dwg_adapter.py
    ocr_adapter.py

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

Status: next.

Scope:

- add `quantity_item`
- add `services/quantity.py`
- generate quantity rows from objects, geometry, attributes, and relations
- support count, length, area, and grouped quantity methods
- export quantity CSV

### M5: Budgeting

Scope:

- add `cost_item`
- add `budget_item`
- add `services/budget.py`
- match quantity items to cost items
- generate project, drawing, discipline, system, and area summaries
- export budget CSV or Excel

### M6: Installation Guidance

Scope:

- add installation templates
- generate `install_task`
- generate `install_dependency`
- generate readable installation instructions
- support object-level and discipline-level installation guidance

### M7: Workflow Planning

Scope:

- group installation tasks by discipline, area, system, and dependency
- produce a simple dependency graph
- detect missing prerequisites
- generate a recommended installation sequence

Recommended first sequence model:

```text
building / structure conditions
  -> supports and hangers
  -> main ducts / pipes / trays
  -> equipment placement
  -> branch connections / cables / controls
  -> insulation / labels
  -> single-equipment commissioning
  -> system commissioning
```

### M8: Real Parser Adapter Layer

Scope:

- add DXF or DWG parser adapter
- convert parser output into normalized JSON
- preserve parser metadata in `cad_meta.raw_meta`
- keep ObjectStore unchanged

Do this only after the normalized import and relation workflow are stable.

### M9: API And UI

Scope:

- expose import, object list, object detail, candidates, relations, quantity, budget, and installation plans through API
- add review UI for candidates and corrections
- add report views for budget and installation workflow

Do not duplicate service logic in the API layer.

## 9. Near-Term Recommended Order

The most practical sequence from the current repository state is:

```text
1. Add quantity_item and quantity generation.
2. Add cost_item, budget_item, and budget generation.
3. Add install_task and installation guidance.
4. Add workflow dependency planning.
5. Connect real DWG/DXF parser adapters.
6. Add API and UI.
```

This order keeps the data foundation strong. Budgeting and installation planning depend on object identity, attributes, geometry, and relations. If those are weak, upper-layer outputs will become fragile flat reports instead of useful engineering workflows.

## 10. Design Rules To Preserve

- Keep `source_file + handle` as the object identity rule.
- Keep importers writing through `ObjectStore`.
- Keep uncertain inference writing to `relation_candidate` first.
- Keep final engineering truth in `relation`.
- Keep human correction auditable through correction tables.
- Keep parser-specific assumptions outside the object store.
- Keep LLM output structured, reviewable, and replaceable.
- Prefer taxonomy and rule configuration over hard-coded discipline logic.
- Add new tables only when the service layer needs durable, auditable outputs.
