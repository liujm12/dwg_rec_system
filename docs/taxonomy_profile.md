# Taxonomy Profile

Round 3 separates object classification from engineering semantics.

The project now uses:

```text
dwg_rec_system/taxonomy/cad_object_taxonomy.json
dwg_rec_system/taxonomy/engineering_class_profiles.json
```

## Base Taxonomy

`cad_object_taxonomy.json` is the primary CAD object taxonomy.

It answers:

```text
What kind of object is this?
```

It is the source for `object_class` and contains:

- `code`
- `name_cn`
- `discipline`
- `parent_code`
- `aliases`
- `attributes`
- `relations`

`TaxonomySeeder.seed_file()` loads this file by default.

## Engineering Profile Overlay

`engineering_class_profiles.json` is an overlay on top of the base taxonomy.

It answers:

```text
How should this object class be used for quantity, budget, installation, and workflow planning?
```

It does not define new object classes and should not be seeded into `object_class`.

Every `class_profiles[].code` must already exist in `cad_object_taxonomy.json`.

## Profile Shape

Each `class_profiles` entry uses this shape:

```json
{
  "code": "VALVE",
  "profile_group": "PIPING",
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

Allowed profile fields:

- `code`
- `profile_group`
- `expected_attributes`
- `relations`
- `budget`
- `installation`
- `description`

Fields such as `name_cn`, `discipline`, `parent_code`, and `aliases` belong to the base taxonomy.

## Approved Profile Groups

Round 3 starts with:

```text
HVAC
PIPING
ELEC
BMS
CLEANROOM
```

These are profile groups for engineering behavior. They do not need to exactly match every `discipline` value in the base taxonomy.

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

## Why This Is An Overlay

The base taxonomy should stay stable because it controls object identity and strict import validation.

Engineering profiles will evolve more often. Budget grouping, installation steps, and workflow prerequisites may vary by project type, region, or company standard.

Keeping them separate avoids two problems:

- creating duplicate object class codes such as `VALVE` and `PLB_VALVE`
- bloating the primary taxonomy with fast-changing engineering behavior

## Relationship To Future Tables

Round 3 deliberately does not add profile-specific database columns.

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
- profile group
- grouped quantity attributes
- future cost item matching rules

Installation services should use:

- `installation.work_package`
- `installation.default_steps`
- `installation.required_predecessors`
- accepted relations such as `located_in`, `connected_to`, `mounted_on`, `powered_by`, and `controlled_by`

Relation and inference services may use:

- `relations`
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
