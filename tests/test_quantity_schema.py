from dwg_rec_system.db import init_database, session


def test_quantity_item_table_exists_with_expected_columns(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(quantity_item)").fetchall()
        }

    assert {
        "id",
        "project_id",
        "drawing_id",
        "source_object_id",
        "class_code",
        "discipline",
        "item_name",
        "spec",
        "unit",
        "quantity",
        "quantity_method",
        "group_key",
        "location",
        "system_code",
        "confidence",
        "source",
        "evidence_json",
        "status",
        "created_at",
        "updated_at",
    } <= columns


def test_quantity_item_accepts_auditable_quantity_row(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        connection.execute(
            """
            INSERT INTO quantity_item(
                id,
                class_code,
                discipline,
                item_name,
                spec,
                unit,
                quantity,
                quantity_method,
                group_key,
                confidence,
                source,
                evidence_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "qty_001",
                "VALVE",
                "PIPING",
                "Valve",
                "DN100 stainless valve",
                "pcs",
                12,
                "count_by_object",
                "VALVE|DN100|stainless",
                0.95,
                "auto",
                '{"method": "count_by_object"}',
            ),
        )
        row = connection.execute(
            "SELECT * FROM quantity_item WHERE id = 'qty_001'"
        ).fetchone()

    assert row["class_code"] == "VALVE"
    assert row["quantity"] == 12
    assert row["status"] == "auto"


def test_quantity_item_rejects_unknown_quantity_method(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        try:
            connection.execute(
                """
                INSERT INTO quantity_item(
                    id, class_code, item_name, unit, quantity, quantity_method
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("qty_bad", "VALVE", "Valve", "pcs", 1, "bad_method"),
            )
            assert False, "expected CHECK constraint failure"
        except Exception as exc:
            assert "CHECK constraint failed" in str(exc)
