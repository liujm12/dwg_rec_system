# PostgreSQL / PostGIS Target

这里预留 PostgreSQL/PostGIS 迁移目录。当前项目尚未引入 PostgreSQL 运行依赖。

目标原则：

- `project/drawing/cad_object/attribute/relation` 保持与 SQLite 语义一致。
- `geometry_wkt + geometry_srid` 迁移为 PostGIS `geometry` 字段。
- `relation_candidate` 保存规则、LLM、解析器的候选结果。
- `relation` 只保存已经接受的工程关系。
- `correction_log` 保存对象、属性、几何、关系的人工修正审计。

建议未来增加：

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE INDEX ... USING GIST (geom);
```
