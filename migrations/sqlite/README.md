# SQLite

SQLite schema 当前由 `dwg_rec_system/schema.sql` 管理。

`dwg_rec_system.db.init_database()` 会执行 schema，并对已有 SQLite 数据库补充新增列。注意：SQLite 对 `CHECK` 和旧唯一约束的在线改造能力有限，生产前如果需要大版本升级，应使用显式迁移脚本重建目标表。

SQLite 专用对象：

- `geometry_rtree`
- `geometry_rtree_map`

这些对象不要迁移到 PostgreSQL，PostgreSQL 侧应改用 PostGIS GiST/SP-GiST 空间索引。
