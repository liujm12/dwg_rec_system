# Normalized CAD Import Format

This document defines the normalized JSON format that external CAD parsers should produce before data enters this project.

The format is intentionally parser-agnostic. A DWG parser, DXF parser, AutoCAD plugin, OCR service, or LLM preprocessing tool should all be able to produce this structure.

## Top-Level Shape

```json
{
  "version": "0.1",
  "project": {
    "code": "DEMO",
    "name": "Demo CAD Recognition Project"
  },
  "drawing": {
    "drawing_no": "E-1001",
    "revision": "C",
    "discipline": "Electrical",
    "sheet": "1",
    "title": "Demo control cabinet layout",
    "source_file": "demo.dwg"
  },
  "objects": []
}
```

## Required Fields

At minimum:

```json
{
  "objects": [
    {
      "class_name": "DCC",
      "source_file": "demo.dwg",
      "handle": "DCC01"
    }
  ]
}
```

For repeatable imports, `source_file + handle` should be stable. If a parser cannot provide a CAD handle, it should generate a deterministic source-local ID.

## Project

Optional. When present, importer should create or reuse a project.

```json
{
  "code": "DEMO",
  "name": "Demo CAD Recognition Project",
  "owner": "Engineering",
  "description": "Demo project"
}
```

Field mapping:

```text
code        -> project.code
name        -> project.name
owner       -> project.owner
description -> project.description
```

## Drawing

Optional but recommended.

```json
{
  "drawing_no": "E-1001",
  "revision": "C",
  "discipline": "Electrical",
  "sheet": "1",
  "title": "Demo control cabinet layout",
  "source_file": "demo.dwg"
}
```

Field mapping:

```text
drawing_no  -> drawing.drawing_no
revision    -> drawing.revision
discipline  -> drawing.discipline
sheet       -> drawing.sheet
title       -> drawing.title
source_file -> drawing.source_file
```

If both object-level `source_file` and drawing-level `source_file` exist, object-level value wins. Otherwise objects may inherit drawing-level `source_file`.

## Object

Example:

```json
{
  "class_name": "DCC",
  "subtype": "DCC_V2",
  "source_file": "demo.dwg",
  "handle": "DCC01",
  "confidence": 0.97,
  "status": "auto",
  "parser_name": "demo_parser",
  "parser_version": "0.1",
  "recognition_model": "rule_demo",
  "recognition_version": "0.1",
  "geometry": {
    "center_x": 1040,
    "center_y": 2030,
    "width": 80,
    "height": 120,
    "rotation": 90
  },
  "cad_meta": {
    "layer": "E-EQUIP",
    "block_name": "DCC_BLOCK",
    "color": "3"
  },
  "attributes": {
    "tag": "DCC-001",
    "vendor": "ABB",
    "model": "AC800M"
  }
}
```

Field mapping:

```text
class_name          -> ObjectInput.class_name
subtype             -> ObjectInput.subtype
source_file         -> ObjectInput.source_file
handle              -> ObjectInput.handle
confidence          -> ObjectInput.confidence
status              -> ObjectInput.status
parser_name         -> ObjectInput.parser_name
parser_version      -> ObjectInput.parser_version
recognition_model   -> ObjectInput.recognition_model
recognition_version -> ObjectInput.recognition_version
geometry            -> GeometryInput
cad_meta            -> CadMetaInput
attributes          -> ObjectInput.attributes
```

`class_id` should normally be resolved by importer from `object_class.code == class_name`. External parser output should use stable `class_name` codes, not internal database IDs.

## Geometry

Bounding box by center:

```json
{
  "center_x": 1000,
  "center_y": 2000,
  "width": 300,
  "height": 500,
  "rotation": 0
}
```

Explicit bounds:

```json
{
  "min_x": 850,
  "min_y": 1750,
  "max_x": 1150,
  "max_y": 2250
}
```

Future geometry fields:

```json
{
  "geometry_type": "polyline",
  "geometry_wkt": "LINESTRING(0 0, 10 10)",
  "geometry_srid": 0,
  "raw_geometry": {
    "vertices": [[0, 0], [10, 10]]
  }
}
```

When both center/size and explicit bounds exist, explicit bounds should be treated as authoritative for spatial indexing.

## CAD Metadata

```json
{
  "layer": "E-EQUIP",
  "block_name": "DCC_BLOCK",
  "color": "3",
  "linetype": "Continuous",
  "owner_block": "MODEL_SPACE",
  "raw_meta": {
    "handle": "DCC01",
    "layout": "Model"
  }
}
```

Keep parser-specific or CAD-vendor-specific details inside `raw_meta`.

## Attributes

Attributes are object-specific domain facts.

```json
{
  "tag": "DCC-001",
  "vendor": "ABB",
  "model": "AC800M",
  "io_count": 64
}
```

Current importer should support a simple object map. A future version may support rich attribute records:

```json
{
  "attributes": [
    {
      "namespace": "default",
      "key": "diameter",
      "value": "DN100",
      "normalized_value": "100",
      "unit": "mm",
      "confidence": 0.95,
      "source": "parser"
    }
  ]
}
```

Round 1 should implement the simple object map first.

## Full Example

```json
{
  "version": "0.1",
  "project": {
    "code": "DEMO",
    "name": "Demo CAD Recognition Project"
  },
  "drawing": {
    "drawing_no": "E-1001",
    "revision": "C",
    "discipline": "Electrical",
    "sheet": "1",
    "title": "Demo control cabinet layout",
    "source_file": "demo.dwg"
  },
  "objects": [
    {
      "class_name": "DCC_RACK",
      "subtype": "RACK_V1",
      "source_file": "demo.dwg",
      "handle": "RACK01",
      "confidence": 0.98,
      "parser_name": "demo_parser",
      "parser_version": "0.1",
      "recognition_model": "rule_demo",
      "recognition_version": "0.1",
      "geometry": {
        "center_x": 1000,
        "center_y": 2000,
        "width": 300,
        "height": 500
      },
      "cad_meta": {
        "layer": "E-EQUIP",
        "block_name": "DCC_RACK_BLOCK",
        "color": "7"
      },
      "attributes": {
        "tag": "RACK-01",
        "vendor": "Generic"
      }
    },
    {
      "class_name": "DCC",
      "subtype": "DCC_V2",
      "source_file": "demo.dwg",
      "handle": "DCC01",
      "confidence": 0.97,
      "parser_name": "demo_parser",
      "parser_version": "0.1",
      "recognition_model": "rule_demo",
      "recognition_version": "0.1",
      "geometry": {
        "center_x": 1040,
        "center_y": 2030,
        "width": 80,
        "height": 120,
        "rotation": 90
      },
      "cad_meta": {
        "layer": "E-EQUIP",
        "block_name": "DCC_BLOCK",
        "color": "3"
      },
      "attributes": {
        "tag": "DCC-001",
        "vendor": "ABB",
        "model": "AC800M"
      }
    }
  ]
}
```

## Importer Error Policy

Round 1 importer should fail fast with clear errors for:

- invalid JSON
- missing `objects`
- object without `class_name`
- object without both object-level and drawing-level `source_file`

Round 1 importer should allow missing:

- project
- drawing
- geometry
- cad_meta
- attributes
- handle, only if there is a clear deterministic fallback strategy

If there is no stable fallback for `handle`, the importer should reject the object because repeat imports would not be safe.

