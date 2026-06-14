PRAGMA foreign_keys = ON;

DROP TRIGGER IF EXISTS trg_geometry_insert_rtree;
DROP TRIGGER IF EXISTS trg_geometry_update_rtree;
DROP TRIGGER IF EXISTS trg_geometry_delete_rtree;

CREATE TABLE IF NOT EXISTS project (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    owner TEXT,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS drawing (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES project(id) ON DELETE SET NULL,
    drawing_no TEXT NOT NULL,
    revision TEXT,
    discipline TEXT,
    sheet TEXT,
    title TEXT,
    source_file TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (drawing_no, revision, sheet)
);

CREATE TABLE IF NOT EXISTS import_job (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES project(id) ON DELETE SET NULL,
    source_file TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
    parser_name TEXT,
    parser_version TEXT,
    error_message TEXT,
    stats_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS object_class (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    parent_code TEXT,
    discipline TEXT,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cad_object (
    id TEXT PRIMARY KEY,
    drawing_id TEXT REFERENCES drawing(id) ON DELETE SET NULL,
    import_job_id TEXT REFERENCES import_job(id) ON DELETE SET NULL,
    class_id TEXT REFERENCES object_class(id) ON DELETE SET NULL,
    source_file TEXT,
    handle TEXT,
    class TEXT NOT NULL,
    subtype TEXT,
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    status TEXT NOT NULL DEFAULT 'auto' CHECK (status IN ('auto', 'manual', 'corrected', 'rejected')),
    parser_name TEXT,
    parser_version TEXT,
    recognition_model TEXT,
    recognition_version TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source_file, handle)
);

CREATE INDEX IF NOT EXISTS idx_cad_object_class ON cad_object(class);
CREATE INDEX IF NOT EXISTS idx_cad_object_drawing ON cad_object(drawing_id);
CREATE INDEX IF NOT EXISTS idx_cad_object_status ON cad_object(status);

CREATE TABLE IF NOT EXISTS geometry (
    object_id TEXT PRIMARY KEY REFERENCES cad_object(id) ON DELETE CASCADE,
    center_x REAL,
    center_y REAL,
    width REAL,
    height REAL,
    rotation REAL NOT NULL DEFAULT 0,
    min_x REAL,
    min_y REAL,
    max_x REAL,
    max_y REAL,
    bbox_json TEXT,
    geometry_type TEXT NOT NULL DEFAULT 'bbox',
    geometry_wkt TEXT,
    geometry_srid INTEGER NOT NULL DEFAULT 0,
    raw_geometry_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS geometry_rtree USING rtree(
    rowid,
    min_x,
    max_x,
    min_y,
    max_y
);

CREATE TABLE IF NOT EXISTS geometry_rtree_map (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id TEXT NOT NULL UNIQUE REFERENCES cad_object(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cad_meta (
    object_id TEXT PRIMARY KEY REFERENCES cad_object(id) ON DELETE CASCADE,
    layer TEXT,
    block_name TEXT,
    color TEXT,
    linetype TEXT,
    owner_block TEXT,
    raw_meta_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS attribute (
    id TEXT PRIMARY KEY,
    object_id TEXT NOT NULL REFERENCES cad_object(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value TEXT,
    normalized_value TEXT,
    unit TEXT,
    namespace TEXT NOT NULL DEFAULT 'default',
    value_type TEXT NOT NULL DEFAULT 'string',
    is_inferred INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    source TEXT NOT NULL DEFAULT 'auto' CHECK (source IN ('auto', 'manual', 'rule', 'import', 'parser', 'llm')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (object_id, namespace, key)
);

CREATE INDEX IF NOT EXISTS idx_attribute_key_value ON attribute(key, value);
CREATE INDEX IF NOT EXISTS idx_attribute_object ON attribute(object_id);

CREATE TABLE IF NOT EXISTS relation (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES cad_object(id) ON DELETE CASCADE,
    target_id TEXT NOT NULL REFERENCES cad_object(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    source TEXT NOT NULL DEFAULT 'auto' CHECK (source IN ('auto', 'manual', 'rule', 'import', 'parser', 'llm')),
    rule_id TEXT REFERENCES rule_template(id) ON DELETE SET NULL,
    candidate_id TEXT REFERENCES relation_candidate(id) ON DELETE SET NULL,
    evidence_json TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'overridden', 'rejected')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source_id, target_id, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_relation_source ON relation(source_id);
CREATE INDEX IF NOT EXISTS idx_relation_target ON relation(target_id);
CREATE INDEX IF NOT EXISTS idx_relation_type ON relation(relation_type);

CREATE TABLE IF NOT EXISTS rule_template (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    version TEXT NOT NULL DEFAULT '1',
    rule_kind TEXT NOT NULL DEFAULT 'spatial',
    source_class TEXT NOT NULL,
    target_class TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    max_distance REAL,
    expression TEXT,
    min_confidence REAL NOT NULL DEFAULT 0.5,
    enabled INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 100,
    config_json TEXT,
    valid_from TEXT,
    valid_to TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_rule_template_enabled ON rule_template(enabled, priority);

CREATE TABLE IF NOT EXISTS relation_candidate (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES cad_object(id) ON DELETE CASCADE,
    target_id TEXT NOT NULL REFERENCES cad_object(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    source TEXT NOT NULL CHECK (source IN ('rule', 'llm', 'parser', 'import')),
    rule_id TEXT REFERENCES rule_template(id) ON DELETE SET NULL,
    inference_job_id TEXT,
    evidence_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'superseded')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source_id, target_id, relation_type, source)
);

CREATE INDEX IF NOT EXISTS idx_relation_candidate_status ON relation_candidate(status);
CREATE INDEX IF NOT EXISTS idx_relation_candidate_source ON relation_candidate(source_id);

CREATE TABLE IF NOT EXISTS quantity_item (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES project(id) ON DELETE SET NULL,
    drawing_id TEXT REFERENCES drawing(id) ON DELETE SET NULL,
    source_object_id TEXT REFERENCES cad_object(id) ON DELETE SET NULL,
    class_code TEXT NOT NULL,
    discipline TEXT,
    item_name TEXT NOT NULL,
    spec TEXT,
    unit TEXT NOT NULL,
    quantity REAL NOT NULL CHECK (quantity >= 0),
    quantity_method TEXT NOT NULL CHECK (
        quantity_method IN (
            'count_by_object',
            'length_by_geometry',
            'area_by_geometry',
            'grouped_count',
            'formula',
            'manual_review'
        )
    ),
    group_key TEXT,
    location TEXT,
    system_code TEXT,
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    source TEXT NOT NULL DEFAULT 'auto' CHECK (
        source IN ('auto', 'manual', 'rule', 'import', 'parser', 'llm')
    ),
    evidence_json TEXT,
    status TEXT NOT NULL DEFAULT 'auto' CHECK (
        status IN ('auto', 'reviewed', 'corrected', 'rejected')
    ),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_quantity_item_project ON quantity_item(project_id);
CREATE INDEX IF NOT EXISTS idx_quantity_item_drawing ON quantity_item(drawing_id);
CREATE INDEX IF NOT EXISTS idx_quantity_item_source_object ON quantity_item(source_object_id);
CREATE INDEX IF NOT EXISTS idx_quantity_item_class ON quantity_item(class_code);
CREATE INDEX IF NOT EXISTS idx_quantity_item_status ON quantity_item(status);
CREATE INDEX IF NOT EXISTS idx_quantity_item_group ON quantity_item(group_key);

CREATE TABLE IF NOT EXISTS grid_axis (
    id TEXT PRIMARY KEY,
    drawing_id TEXT REFERENCES drawing(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('X', 'Y')),
    position REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (drawing_id, name, direction)
);

CREATE TABLE IF NOT EXISTS object_axis (
    object_id TEXT PRIMARY KEY REFERENCES cad_object(id) ON DELETE CASCADE,
    axis_x_id TEXT REFERENCES grid_axis(id) ON DELETE SET NULL,
    axis_y_id TEXT REFERENCES grid_axis(id) ON DELETE SET NULL,
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    source TEXT NOT NULL DEFAULT 'auto' CHECK (source IN ('auto', 'manual', 'rule', 'import')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS manual_relation (
    id TEXT PRIMARY KEY,
    original_relation_id TEXT REFERENCES relation(id) ON DELETE SET NULL,
    source_id TEXT NOT NULL REFERENCES cad_object(id) ON DELETE CASCADE,
    old_target_id TEXT REFERENCES cad_object(id) ON DELETE SET NULL,
    new_target_id TEXT NOT NULL REFERENCES cad_object(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    reason TEXT,
    operator TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS correction_log (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('object', 'relation', 'attribute', 'geometry', 'drawing')),
    entity_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    operator TEXT,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_correction_log_entity ON correction_log(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS artifact (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES project(id) ON DELETE SET NULL,
    drawing_id TEXT REFERENCES drawing(id) ON DELETE SET NULL,
    artifact_type TEXT NOT NULL,
    name TEXT NOT NULL,
    file_path TEXT,
    format TEXT,
    input_json TEXT,
    generator TEXT,
    generator_version TEXT,
    rule_version TEXT,
    status TEXT NOT NULL DEFAULT 'created' CHECK (status IN ('created', 'exported', 'failed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
