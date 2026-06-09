# Database Migration Notes

当前实现仍使用 SQLite，适合原型、单机验证和无依赖本地运行。为了后续迁移到 PostgreSQL/PostGIS，数据库设计按下面边界维护：

- 通用实体表：`project`、`drawing`、`cad_object`、`attribute`、`relation`、`relation_candidate`、`correction_log`、`artifact`。
- SQLite 专用空间索引：`geometry_rtree`、`geometry_rtree_map`。
- PostGIS 迁移目标：保留 `geometry.min_x/min_y/max_x/max_y` 作为 bbox 缓存，同时把 `geometry_wkt/geometry_srid` 映射到 PostGIS `geometry` 字段。

后续如果正式切 PostgreSQL，优先迁移这些字段：

```text
geometry.geometry_wkt   -> ST_GeomFromText(geometry_wkt, geometry_srid)
geometry.geometry_srid  -> SRID
geometry bbox columns   -> generated/cache columns or spatial query fallback
relation_candidate      -> LLM/rule/parser suggestions
relation                -> accepted engineering graph edges
correction_log          -> audit trail
```

不要把 LLM 建议直接写成最终工程关系。LLM、规则、解析器都先写入 `relation_candidate`，只有接受后的结果进入 `relation`。
