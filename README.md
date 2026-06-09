# CAD 图纸识别系统初版

这个仓库已经按 `ai_cad_read_design.txt` 的设计落地为一个可运行的数据库和架构骨架。

当前版本重点：

- `Object + Relation + Context` 作为核心模型，而不是围绕单一 `Device` 表设计。
- `geometry` 和 `cad_meta` 独立存储，方便后续定位识别错误。
- `attribute` 使用 EAV 扩展模型，支持 PLC、DCS、MCC、仪表等不同对象类型。
- `relation`、`rule_template`、`manual_relation` 从第一版预留，用于推理和人工修正。
- SQLite R-Tree 空间索引已接入，后续可以迁移到 PostGIS。
- 已增加 `project`、`object_class`、`relation_candidate`、`correction_log`、`artifact`，用于多项目、分类字典、候选推理、审计和导出物追踪。
- LLM/规则/解析器的建议关系先进入 `relation_candidate`，接受后再进入最终 `relation`。

## 目录

```text
dwg_rec_system/
  db.py                 数据库连接和初始化
  schema.sql            全量数据库表结构
  models.py             领域数据结构
  repositories.py       数据访问层
  cli.py                命令行入口
  services/
    object_store.py     对象入库服务
    relation_engine.py  规则推理服务
    spatial_index.py    nearest/contains/overlap 查询
    exports.py          CSV 导出
migrations/
  sqlite/                SQLite 迁移说明
  postgres/              PostgreSQL/PostGIS 迁移目标说明
tests/
  test_database_flow.py 基础验证
```

## 快速开始

```powershell
python -m dwg_rec_system.cli init-db
python -m dwg_rec_system.cli seed-demo
python -m dwg_rec_system.cli list-objects
python -m dwg_rec_system.cli infer-relations
python -m dwg_rec_system.cli export-csv
```

默认数据库文件为：

```text
data/dwg_rec_system.db
```

也可以通过环境变量指定：

```powershell
$env:DWG_REC_DB="D:\path\to\cad.db"
python -m dwg_rec_system.cli init-db
```

## 后续扩展方向

V1 继续接 CAD 解析器，把 DWG 中的 block、text、line、polyline 等原始实体转换为 `cad_object`、`geometry`、`cad_meta`、`attribute`。

V2 增加更多规则模板和空间推理策略，生成安装表、设备清单。

V3 加入轴位计算、电气连接、层级关系，生成 IO Mapping、Cable Schedule、Installation Schedule。

V4 将 `relation` 映射到 Neo4j 或 Apache AGE，形成完整工程知识图谱。
