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

CREATE TABLE IF NOT EXISTS cost_item (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    discipline TEXT,
    class_code TEXT NOT NULL,
    spec_pattern TEXT,
    unit TEXT NOT NULL,
    unit_price_material REAL NOT NULL DEFAULT 0 CHECK (unit_price_material >= 0),
    unit_price_labor REAL NOT NULL DEFAULT 0 CHECK (unit_price_labor >= 0),
    unit_price_machine REAL NOT NULL DEFAULT 0 CHECK (unit_price_machine >= 0),
    currency TEXT NOT NULL DEFAULT 'CNY',
    region TEXT,
    version TEXT,
    effective_from TEXT,
    effective_to TEXT,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cost_item_class_unit ON cost_item(class_code, unit);
CREATE INDEX IF NOT EXISTS idx_cost_item_status ON cost_item(status);
CREATE INDEX IF NOT EXISTS idx_cost_item_discipline ON cost_item(discipline);

CREATE TABLE IF NOT EXISTS budget_item (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES project(id) ON DELETE SET NULL,
    drawing_id TEXT REFERENCES drawing(id) ON DELETE SET NULL,
    quantity_item_id TEXT REFERENCES quantity_item(id) ON DELETE SET NULL,
    cost_item_id TEXT REFERENCES cost_item(id) ON DELETE SET NULL,
    class_code TEXT,
    discipline TEXT,
    item_name TEXT NOT NULL,
    spec TEXT,
    unit TEXT NOT NULL,
    quantity REAL NOT NULL CHECK (quantity >= 0),
    unit_price_material REAL NOT NULL DEFAULT 0 CHECK (unit_price_material >= 0),
    unit_price_labor REAL NOT NULL DEFAULT 0 CHECK (unit_price_labor >= 0),
    unit_price_machine REAL NOT NULL DEFAULT 0 CHECK (unit_price_machine >= 0),
    material_cost REAL NOT NULL DEFAULT 0 CHECK (material_cost >= 0),
    labor_cost REAL NOT NULL DEFAULT 0 CHECK (labor_cost >= 0),
    machine_cost REAL NOT NULL DEFAULT 0 CHECK (machine_cost >= 0),
    total_cost REAL NOT NULL DEFAULT 0 CHECK (total_cost >= 0),
    pricing_source TEXT NOT NULL DEFAULT 'auto',
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence_json TEXT,
    status TEXT NOT NULL DEFAULT 'auto' CHECK (
        status IN ('auto', 'review', 'matched', 'unmatched', 'corrected', 'rejected')
    ),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_budget_item_project ON budget_item(project_id);
CREATE INDEX IF NOT EXISTS idx_budget_item_drawing ON budget_item(drawing_id);
CREATE INDEX IF NOT EXISTS idx_budget_item_quantity ON budget_item(quantity_item_id);
CREATE INDEX IF NOT EXISTS idx_budget_item_cost ON budget_item(cost_item_id);
CREATE INDEX IF NOT EXISTS idx_budget_item_class ON budget_item(class_code);
CREATE INDEX IF NOT EXISTS idx_budget_item_status ON budget_item(status);

CREATE TABLE IF NOT EXISTS install_task (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES project(id) ON DELETE SET NULL,
    drawing_id TEXT REFERENCES drawing(id) ON DELETE SET NULL,
    object_id TEXT REFERENCES cad_object(id) ON DELETE SET NULL,
    class_code TEXT NOT NULL,
    discipline TEXT,
    task_name TEXT NOT NULL,
    work_package TEXT,
    location TEXT,
    system_code TEXT,
    priority INTEGER NOT NULL DEFAULT 100,
    estimated_duration REAL,
    crew_type TEXT,
    source TEXT NOT NULL DEFAULT 'auto' CHECK (
        source IN ('auto', 'manual', 'rule', 'import', 'parser', 'llm')
    ),
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence_json TEXT,
    status TEXT NOT NULL DEFAULT 'auto' CHECK (
        status IN ('auto', 'review', 'ready', 'blocked', 'corrected', 'rejected', 'done')
    ),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_install_task_project ON install_task(project_id);
CREATE INDEX IF NOT EXISTS idx_install_task_drawing ON install_task(drawing_id);
CREATE INDEX IF NOT EXISTS idx_install_task_object ON install_task(object_id);
CREATE INDEX IF NOT EXISTS idx_install_task_class ON install_task(class_code);
CREATE INDEX IF NOT EXISTS idx_install_task_status ON install_task(status);

CREATE TABLE IF NOT EXISTS install_dependency (
    id TEXT PRIMARY KEY,
    predecessor_task_id TEXT NOT NULL REFERENCES install_task(id) ON DELETE CASCADE,
    successor_task_id TEXT NOT NULL REFERENCES install_task(id) ON DELETE CASCADE,
    dependency_type TEXT NOT NULL CHECK (
        dependency_type IN (
            'finish_to_start',
            'start_to_start',
            'inspection_before',
            'pressure_test_before',
            'power_before_commissioning',
            'profile_prerequisite'
        )
    ),
    reason TEXT,
    source TEXT NOT NULL DEFAULT 'auto' CHECK (
        source IN ('auto', 'manual', 'rule', 'import', 'parser', 'llm')
    ),
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence_json TEXT,
    status TEXT NOT NULL DEFAULT 'auto' CHECK (
        status IN ('auto', 'review', 'corrected', 'rejected')
    ),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_install_dependency_predecessor
    ON install_dependency(predecessor_task_id);
CREATE INDEX IF NOT EXISTS idx_install_dependency_successor
    ON install_dependency(successor_task_id);
CREATE INDEX IF NOT EXISTS idx_install_dependency_status
    ON install_dependency(status);

CREATE TABLE IF NOT EXISTS install_instruction (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES install_task(id) ON DELETE CASCADE,
    instruction_text TEXT NOT NULL,
    generator TEXT NOT NULL DEFAULT 'template',
    generator_version TEXT NOT NULL DEFAULT '0.1',
    source_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_install_instruction_task
    ON install_instruction(task_id);

CREATE TABLE IF NOT EXISTS workflow_plan (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES project(id) ON DELETE SET NULL,
    drawing_id TEXT REFERENCES drawing(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    scope_json TEXT,
    generator TEXT NOT NULL DEFAULT 'workflow_plan_generator',
    generator_version TEXT NOT NULL DEFAULT '0.1',
    status TEXT NOT NULL DEFAULT 'review' CHECK (
        status IN ('draft', 'review', 'ready', 'superseded', 'rejected')
    ),
    summary_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_workflow_plan_project ON workflow_plan(project_id);
CREATE INDEX IF NOT EXISTS idx_workflow_plan_drawing ON workflow_plan(drawing_id);
CREATE INDEX IF NOT EXISTS idx_workflow_plan_status ON workflow_plan(status);

CREATE TABLE IF NOT EXISTS workflow_step (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES workflow_plan(id) ON DELETE CASCADE,
    task_id TEXT NOT NULL REFERENCES install_task(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL,
    sequence_group TEXT,
    discipline TEXT,
    work_package TEXT,
    location TEXT,
    system_code TEXT,
    dependency_count INTEGER NOT NULL DEFAULT 0,
    blocked_by_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'planned' CHECK (
        status IN ('planned', 'review', 'blocked', 'unplanned', 'done', 'rejected')
    ),
    evidence_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (plan_id, task_id)
);

CREATE INDEX IF NOT EXISTS idx_workflow_step_plan ON workflow_step(plan_id);
CREATE INDEX IF NOT EXISTS idx_workflow_step_task ON workflow_step(task_id);
CREATE INDEX IF NOT EXISTS idx_workflow_step_status ON workflow_step(status);
CREATE INDEX IF NOT EXISTS idx_workflow_step_sequence ON workflow_step(plan_id, sequence_no);

CREATE TABLE IF NOT EXISTS workflow_issue (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES workflow_plan(id) ON DELETE CASCADE,
    task_id TEXT REFERENCES install_task(id) ON DELETE SET NULL,
    dependency_id TEXT REFERENCES install_dependency(id) ON DELETE SET NULL,
    severity TEXT NOT NULL CHECK (severity IN ('error', 'warning', 'info')),
    category TEXT NOT NULL CHECK (
        category IN (
            'cycle',
            'missing_dependency_task',
            'review_dependency',
            'blocked_predecessor',
            'unplanned_task',
            'task_needs_review',
            'missing_scope'
        )
    ),
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    evidence_json TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (
        status IN ('open', 'accepted', 'resolved', 'rejected')
    ),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_workflow_issue_plan ON workflow_issue(plan_id);
CREATE INDEX IF NOT EXISTS idx_workflow_issue_task ON workflow_issue(task_id);
CREATE INDEX IF NOT EXISTS idx_workflow_issue_dependency ON workflow_issue(dependency_id);
CREATE INDEX IF NOT EXISTS idx_workflow_issue_severity ON workflow_issue(severity);
CREATE INDEX IF NOT EXISTS idx_workflow_issue_category ON workflow_issue(category);
CREATE INDEX IF NOT EXISTS idx_workflow_issue_status ON workflow_issue(status);

CREATE TABLE IF NOT EXISTS source_document (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES project(id) ON DELETE SET NULL,
    source_uri TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL DEFAULT 'unknown' CHECK (
        source_type IN ('pdf', 'dwg', 'dxf', 'image', 'cad_export', 'json', 'unknown')
    ),
    file_hash TEXT,
    title TEXT,
    parser_name TEXT,
    parser_version TEXT,
    metadata_json TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'archived', 'failed')
    ),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_source_document_project ON source_document(project_id);
CREATE INDEX IF NOT EXISTS idx_source_document_status ON source_document(status);

CREATE TABLE IF NOT EXISTS drawing_page (
    id TEXT PRIMARY KEY,
    source_document_id TEXT NOT NULL REFERENCES source_document(id) ON DELETE CASCADE,
    drawing_id TEXT REFERENCES drawing(id) ON DELETE SET NULL,
    page_no INTEGER,
    layout_name TEXT,
    width REAL,
    height REAL,
    unit TEXT,
    scale TEXT,
    rotation REAL NOT NULL DEFAULT 0,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source_document_id, page_no, layout_name)
);

CREATE INDEX IF NOT EXISTS idx_drawing_page_source ON drawing_page(source_document_id);
CREATE INDEX IF NOT EXISTS idx_drawing_page_drawing ON drawing_page(drawing_id);

CREATE TABLE IF NOT EXISTS drawing_primitive (
    id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL REFERENCES drawing_page(id) ON DELETE CASCADE,
    source_local_id TEXT NOT NULL,
    primitive_type TEXT NOT NULL DEFAULT 'unknown' CHECK (
        primitive_type IN (
            'line',
            'polyline',
            'path',
            'rect',
            'circle',
            'arc',
            'text',
            'image',
            'block',
            'symbol',
            'unknown'
        )
    ),
    geometry_json TEXT,
    bbox_json TEXT,
    text TEXT,
    style_json TEXT,
    raw_json TEXT,
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (page_id, source_local_id)
);

CREATE INDEX IF NOT EXISTS idx_drawing_primitive_page ON drawing_primitive(page_id);
CREATE INDEX IF NOT EXISTS idx_drawing_primitive_type ON drawing_primitive(primitive_type);

CREATE TABLE IF NOT EXISTS recognition_candidate (
    id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL REFERENCES drawing_page(id) ON DELETE CASCADE,
    source_local_id TEXT NOT NULL,
    candidate_type TEXT NOT NULL DEFAULT 'unknown' CHECK (
        candidate_type IN ('object', 'text_label', 'attribute', 'relation_hint', 'geometry_group', 'unknown')
    ),
    class_code TEXT,
    label TEXT,
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    source TEXT NOT NULL CHECK (
        source IN ('rule', 'parser', 'ocr', 'cv', 'llm', 'manual', 'import')
    ),
    model_name TEXT,
    model_version TEXT,
    geometry_json TEXT,
    bbox_json TEXT,
    attributes_json TEXT,
    evidence_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'accepted', 'rejected', 'superseded', 'merged')
    ),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (page_id, source_local_id)
);

CREATE INDEX IF NOT EXISTS idx_recognition_candidate_page ON recognition_candidate(page_id);
CREATE INDEX IF NOT EXISTS idx_recognition_candidate_class ON recognition_candidate(class_code);
CREATE INDEX IF NOT EXISTS idx_recognition_candidate_status ON recognition_candidate(status);

CREATE TABLE IF NOT EXISTS recognition_candidate_primitive (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES recognition_candidate(id) ON DELETE CASCADE,
    primitive_id TEXT NOT NULL REFERENCES drawing_primitive(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'context' CHECK (
        role IN ('geometry', 'text', 'symbol', 'anchor', 'context', 'negative')
    ),
    weight REAL NOT NULL DEFAULT 1.0,
    evidence_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (candidate_id, primitive_id, role)
);

CREATE INDEX IF NOT EXISTS idx_candidate_primitive_candidate
    ON recognition_candidate_primitive(candidate_id);
CREATE INDEX IF NOT EXISTS idx_candidate_primitive_primitive
    ON recognition_candidate_primitive(primitive_id);

CREATE TABLE IF NOT EXISTS object_hypothesis (
    id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL REFERENCES drawing_page(id) ON DELETE CASCADE,
    source_document_id TEXT NOT NULL REFERENCES source_document(id) ON DELETE CASCADE,
    class_code TEXT NOT NULL,
    subtype TEXT,
    source_local_id TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    geometry_json TEXT,
    bbox_json TEXT,
    attributes_json TEXT,
    evidence_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'accepted', 'rejected', 'merged', 'superseded')
    ),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (page_id, source_local_id)
);

CREATE INDEX IF NOT EXISTS idx_object_hypothesis_page ON object_hypothesis(page_id);
CREATE INDEX IF NOT EXISTS idx_object_hypothesis_source ON object_hypothesis(source_document_id);
CREATE INDEX IF NOT EXISTS idx_object_hypothesis_class ON object_hypothesis(class_code);
CREATE INDEX IF NOT EXISTS idx_object_hypothesis_status ON object_hypothesis(status);

CREATE TABLE IF NOT EXISTS hypothesis_candidate (
    id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL REFERENCES object_hypothesis(id) ON DELETE CASCADE,
    candidate_id TEXT NOT NULL REFERENCES recognition_candidate(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'primary' CHECK (
        role IN ('primary', 'attribute', 'label', 'geometry', 'context', 'negative')
    ),
    weight REAL NOT NULL DEFAULT 1.0,
    evidence_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (hypothesis_id, candidate_id, role)
);

CREATE INDEX IF NOT EXISTS idx_hypothesis_candidate_hypothesis
    ON hypothesis_candidate(hypothesis_id);
CREATE INDEX IF NOT EXISTS idx_hypothesis_candidate_candidate
    ON hypothesis_candidate(candidate_id);

CREATE TABLE IF NOT EXISTS hypothesis_to_object (
    id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL UNIQUE REFERENCES object_hypothesis(id) ON DELETE CASCADE,
    object_id TEXT NOT NULL REFERENCES cad_object(id) ON DELETE CASCADE,
    accepted_by TEXT,
    acceptance_method TEXT NOT NULL DEFAULT 'manual' CHECK (
        acceptance_method IN ('manual', 'rule', 'threshold', 'import')
    ),
    evidence_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_hypothesis_to_object_object
    ON hypothesis_to_object(object_id);

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
    entity_type TEXT NOT NULL CHECK (
        entity_type IN (
            'object',
            'relation',
            'relation_candidate',
            'recognition_candidate',
            'object_hypothesis',
            'attribute',
            'geometry',
            'drawing'
        )
    ),
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
