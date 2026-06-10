# CAD 图纸识别系统

基于 `Object + Relation + Context` 核心模型的工程图纸识别数据基础，支持从标准化 CAD 解析结果导入对象、空间查询、规则关系推理和 CSV 导出。

## 核心架构

- `Object + Relation + Context` 作为核心模型，所有识别物统一走 `cad_object` 表。
- `geometry` 和 `cad_meta` 独立存储，支持空间索引和原始 CAD 信息回溯。
- `attribute` 使用 EAV 扩展模型，灵活支持不同设备类型的属性。
- 推理链路严格遵循 `relation_candidate → accept → relation`，审计可追溯。
- SQLite R-Tree 空间索引，预留 PostGIS 迁移路径。
- 完整审计表：`correction_log`、`manual_relation`。

## 目录

```text
dwg_rec_system/
  db.py                 数据库连接和初始化
  schema.sql            全量数据库表结构
  models.py             领域数据结构（ObjectInput/GeometryInput/CadMetaInput）
  repositories.py       数据访问层
  cli.py                命令行入口
  importers/
    normalized_json.py  标准化 JSON 导入器
  services/
    object_store.py     对象入库服务
    relation_engine.py  规则推理服务
    spatial_index.py    nearest/contains/overlap 查询
    exports.py          CSV 导出
    taxonomy.py         分类字典播种
  taxonomy/
    cleanroom_cad_taxonomy.json  无尘室 CAD 分类字典 (v0.2.0, 164 类)
migrations/
  sqlite/               SQLite 迁移说明
  postgres/             PostgreSQL/PostGIS 迁移目标说明
tests/
  test_database_flow.py     基础对象/空间/关系流程
  test_normalized_import.py 标准化导入测试
  test_seed_taxonomy.py     分类字典播种测试
  test_integration.py       端到端集成测试
  test_taxonomy.py          分类字典结构验证
```

## 快速开始

### 1. 初始化数据库 + 播种分类字典

```powershell
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy
```

`seed-taxonomy` 会导入 164 个无尘室 CAD 对象分类（来自 `dwg_rec_system/taxonomy/cleanroom_cad_taxonomy.json`），可重复运行不重复创建。

### 2. 导入标准化 CAD 解析结果

```powershell
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json
python -m dwg_rec_system.cli list-objects
```

导入格式见 `docs/import_format.md`。同一个 `source_file + handle` 重复导入会更新对象而非创建重复记录。

### 3. 快速演示（跳过导入，直接造数据）

```powershell
python -m dwg_rec_system.cli seed-demo
python -m dwg_rec_system.cli infer-relations
python -m dwg_rec_system.cli export-csv
```

### 4. 运行测试

```powershell
python -m pytest -q
```

默认数据库文件为 `data/dwg_rec_system.db`，可通过环境变量指定：

```powershell
$env:DWG_REC_DB="D:\path\to\cad.db"
python -m dwg_rec_system.cli init-db
```

## CLI 命令汇总

| 命令 | 说明 |
|------|------|
| `init-db` | 创建/重建数据库 schema |
| `seed-taxonomy` | 播种 164 类对象分类字典（幂等） |
| `import-json --input <文件>` | 导入标准化 JSON 解析结果（幂等） |
| `list-objects [--class-name]` | 列出已导入对象 |
| `nearest <对象ID> [--target-class] [--limit]` | 空间最近邻查询 |
| `seed-demo` | 插入演示数据 + 规则 |
| `infer-relations` | 运行规则推理 |
| `export-csv [--output]` | CSV 导出 |

## 完整工作流

```powershell
# 初始化
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-taxonomy

# 导入外部解析结果
python -m dwg_rec_system.cli import-json --input samples/demo_parsed.json

# 查看 + 推理 + 导出
python -m dwg_rec_system.cli list-objects
python -m dwg_rec_system.cli infer-relations
python -m dwg_rec_system.cli export-csv
```

## 后续路线

| 里程碑 | 目标 |
|--------|------|
| M1 ✅ | 标准化 JSON 导入 + 分类字典播种（已完成） |
| M2 | DWG/DXF 解析器适配层 |
| M3 | 更强规则推理（contains/labels/connected_to/axis） |
| M4 | 人工审核与修正工作流 |
| M5 | API 层 (FastAPI) |
| M6 | 本地 LLM 推理层 |
| M7 | PostgreSQL/PostGIS 生产迁移 |
