# 2026-06-05 工作总结

## 今日完成

- 阅读并整理了 `ai_cad_read_design.txt`，确认 CAD 图纸识别系统的核心模型应围绕 `Object + Relation + Context`，而不是单一 `Device` 表。
- 搭建了初版 Python 项目结构，包含数据库初始化、领域模型、仓储层、服务层、CLI 和测试。
- 实现了 SQLite 数据库 schema，覆盖 `drawing`、`cad_object`、`geometry`、`cad_meta`、`attribute`、`relation`、`rule_template`、`grid_axis`、`object_axis`、`manual_relation`、`import_job` 等基础表。
- 接入 SQLite R-Tree 空间索引，支持 `nearest`、`contains_point`、`overlap` 等空间查询能力，为后续 PostGIS 迁移保留 bbox 数据。
- 实现 `ObjectStore`，支持对象、几何、CAD 元信息和 EAV 属性一起入库。
- 实现 `RelationEngine`，当前可根据规则和空间距离推理 `mounted_on` 关系。
- 实现 CLI 工作流：初始化数据库、插入 demo 数据、列出对象、推理关系、导出 CSV。
- 根据 `local_deployment_plan.txt` 评估本地部署要求，确认当前原型方向正确，但需要为 PostgreSQL/PostGIS、LLM 推理层、候选关系、人工修正审计和多项目交付提前预留架构。
- 对数据库和架构做了面向未来的适配改造：
  - 新增 `project`，支持多项目。
  - 新增 `object_class`，支持对象分类字典。
  - 新增 `relation_candidate`，让规则、LLM、解析器先产出候选关系，接受后再进入正式 `relation`。
  - 新增 `correction_log`，支持对象、关系、属性、几何的通用人工修正审计。
  - 新增 `artifact`，用于追踪 BOM、Excel、安装表、IO Mapping 等生成物。
  - `geometry` 增加 `geometry_type`、`geometry_wkt`、`geometry_srid`，为 PostGIS 迁移预留。
  - `attribute` 增加 `namespace`、`normalized_value`、`unit`、`is_inferred`，支持标准化属性和推理属性。
  - `rule_template` 增加 `version`、`rule_kind`、`expression`、`valid_from`、`valid_to`，支持规则版本化。
- 增加兼容迁移逻辑，已有 SQLite 数据库执行 `init-db` 时可以自动补新增列。
- 增加迁移说明目录：
  - `migrations/README.md`
  - `migrations/sqlite/README.md`
  - `migrations/postgres/README.md`
- 更新 README，记录当前架构、运行命令和后续演进方向。

## 当前验证状态

- `python -m pytest -q` 已通过，结果为 `1 passed`。
- `python -m dwg_rec_system.cli init-db` 可初始化或补齐当前 SQLite 数据库。
- `python -m dwg_rec_system.cli seed-demo` 可幂等插入 demo 项目和对象。
- `python -m dwg_rec_system.cli infer-relations` 可生成候选关系并接受为正式关系。
- `python -m dwg_rec_system.cli export-csv` 可导出对象清单。

当前 demo 数据库状态：

```text
project: 1
object_class: 2
cad_object: 2
relation_candidate: 1
relation: 1
correction_log: 0
artifact: 0
```

## 关键设计结论

- 当前阶段继续使用 SQLite 是合理的，适合原型、本地单机验证和低依赖运行。
- 数据库结构已经开始向 PostgreSQL/PostGIS 迁移目标靠拢，尤其是 `geometry_wkt`、`geometry_srid` 和 bbox 缓存字段。
- 以后不要让 LLM 直接读 DWG，也不要让 LLM 直接写最终关系。正确路径是：

```text
DWG -> 结构化 Object Store -> rule/LLM/parser 产生 relation_candidate -> 接受后写入 relation
```

- 工业交付路径应坚持：

```text
规则优先 + LLM 辅助 + 人工可覆盖 + 全链路可审计
```

## 重要文件

- `dwg_rec_system/schema.sql`：当前核心数据库结构。
- `dwg_rec_system/db.py`：数据库连接、初始化和兼容迁移。
- `dwg_rec_system/models.py`：输入数据模型。
- `dwg_rec_system/repositories.py`：项目、对象、属性、关系、候选关系、修正日志等仓储。
- `dwg_rec_system/services/object_store.py`：对象入库服务。
- `dwg_rec_system/services/spatial_index.py`：空间索引服务。
- `dwg_rec_system/services/relation_engine.py`：规则关系推理服务。
- `dwg_rec_system/services/exports.py`：CSV 导出服务。
- `dwg_rec_system/cli.py`：命令行入口。
- `tests/test_database_flow.py`：基础流程测试。
- `migrations/`：SQLite 与 PostgreSQL/PostGIS 迁移说明。
- `local_deployment_plan.txt`：本地部署和 LLM 层设计要求。

## 后续建议

- 下一步优先实现 CAD 解析输入接口，把真实 DWG 解析结果转换为 `ObjectInput`。
- 之后再增加 Backend API，例如 FastAPI，作为 UI、CAD 插件、LLM Server 的统一入口。
- LLM 层建议先做接口抽象，默认 `rule_only`，再接 Ollama/vLLM。
- 正式本地交付前，再补 Docker Compose、PostgreSQL/PostGIS schema 和离线部署文档。
