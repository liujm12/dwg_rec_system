# Taxonomy Profile

Round 3 introduces a multi-discipline taxonomy profile for future quantity takeoff, budgeting, installation guidance, and workflow planning.

The profile is a JSON engineering dictionary. It is not a new database schema and it is not parser-specific recognition logic.

## File

```text
dwg_rec_system/taxonomy/multi_discipline_taxonomy.json
```

The initial profile covers:

```text
HVAC
PLUMBING
ELEC
BAS_ICA
CLEANROOM
```

## Purpose

The profile gives later services a shared source for:

- stable object class codes
- discipline ownership
- common aliases
- expected attributes
- relation hints
- budget quantity hints
- installation step hints

This keeps engineering knowledge in data instead of scattering it through hard-coded Python conditionals.

## Shape

Each `object_classes` entry uses this shape:

```json
{
  "code": "PLB_VALVE",
  "name_cn": "Valve",
  "discipline": "PLUMBING",
  "parent_code": "PLB_PIPE_ACCESSORY",
  "aliases": ["valve", "manual valve", "control valve"],
  "expected_attributes": [
    "tag",
    "diameter",
    "valve_type",
    "material",
    "pressure_rating",
    "medium"
  ],
  "relations": [
    "installed_on",
    "connected_to",
    "located_in"
  ],
  "budget": {
    "unit": "pcs",
    "quantity_method": "count_by_object",
    "group_by": ["diameter", "valve_type", "material"]
  },
  "installation": {
    "work_package": "pipe accessory installation",
    "default_steps": [
      "verify valve spec",
      "confirm flow direction",
      "install valve",
      "inspect sealing",
      "tag valve"
    ],
    "required_predecessors": ["PIPE_SECTION_READY"]
  }
}
```

Allowed fields:

- `code`
- `name_cn`
- `discipline`
- `parent_code`
- `aliases`
- `expected_attributes`
- `relations`
- `budget`
- `installation`
- `description`

## Approved Quantity Methods

Round 3 validates these method names:

```text
count_by_object
length_by_geometry
area_by_geometry
grouped_count
formula
manual_review
```

Meaning:

- `count_by_object`: one quantity row per counted object or grouped object set.
- `length_by_geometry`: derive quantity from line/polyline/path length.
- `area_by_geometry`: derive quantity from area, bbox, or surface logic.
- `grouped_count`: count by selected attributes such as diameter, material, or voltage.
- `formula`: calculate from attributes and geometry with a declared formula in a later round.
- `manual_review`: keep the object in the profile but require manual quantity review.

## Relationship To `object_class`

The current database table `object_class` stores only:

```text
code
name
parent_code
discipline
description
```

Round 3 deliberately does not add profile-specific columns.

`TaxonomySeeder` maps profile entries as follows:

```text
code       -> object_class.code
name_cn    -> object_class.name
parent_code -> object_class.parent_code
discipline -> object_class.discipline
profile hints -> object_class.description
```

For now, aliases, expected attributes, relations, budget hints, and installation hints are summarized into `description`. This is good enough for seeding and review while the profile shape is still evolving.

Future rounds may promote stable fields into dedicated tables such as:

```text
object_class_profile
class_attribute_definition
class_budget_rule
class_install_template
```

That should happen only after quantity, budget, and installation services prove which fields need durable querying.

## How Future Services Should Use It

Quantity services should use:

- `budget.unit`
- `budget.quantity_method`
- `budget.group_by`
- `expected_attributes`
- object geometry and accepted relations

Budget services should use:

- class code
- discipline
- grouped quantity attributes
- future cost item matching rules

Installation services should use:

- `installation.work_package`
- `installation.default_steps`
- `installation.required_predecessors`
- accepted relations such as `located_in`, `connected_to`, `mounted_on`, `powered_by`, and `controlled_by`

Relation and inference services may use:

- `relations`
- `aliases`
- `expected_attributes`

The profile should help services make better decisions, but it should not bypass the existing system boundaries:

```text
importers -> ObjectStore
inference -> relation_candidate
accepted truth -> relation
manual change -> correction_log
```

## Round 3 Boundaries

Round 3 intentionally avoids:

- schema changes
- quantity tables
- budget tables
- installation runtime logic
- DWG/DXF parser adapters
- API or UI work
- LLM integration

This keeps the project in a clean design phase for the engineering dictionary before durable quantity and budget outputs are introduced.
