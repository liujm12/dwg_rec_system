from dwg_rec_system.db import init_database, session
from dwg_rec_system.models import GeometryInput, ObjectInput, RuleTemplateInput
from dwg_rec_system.repositories import RelationRepository, seed_rules
from dwg_rec_system.services.object_store import ObjectStore
from dwg_rec_system.services.relation_engine import RelationEngine
from dwg_rec_system.services.spatial_index import SpatialIndex


def test_object_spatial_and_relation_flow(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    with session(db_path) as connection:
        store = ObjectStore(connection)
        rack_id = store.create_object(
            ObjectInput(
                class_name="DCC_RACK",
                geometry=GeometryInput(center_x=100, center_y=100, width=100, height=100),
                attributes={"tag": "RACK-01"},
            )
        )
        dcc_id = store.create_object(
            ObjectInput(
                class_name="DCC",
                geometry=GeometryInput(center_x=120, center_y=130, width=10, height=10),
                attributes={"tag": "DCC-001"},
            )
        )
        seed_rules(
            connection,
            [
                RuleTemplateInput(
                    name="dcc to rack",
                    source_class="DCC",
                    target_class="DCC_RACK",
                    relation_type="mounted_on",
                    max_distance=80,
                    min_confidence=0.5,
                )
            ],
        )

        nearest = SpatialIndex(connection).nearest(dcc_id, "DCC_RACK")
        assert nearest[0]["id"] == rack_id

        inferred = RelationEngine(connection).infer()
        assert inferred
        candidates = connection.execute("SELECT * FROM relation_candidate").fetchall()
        assert len(candidates) == 1
        assert candidates[0]["status"] == "accepted"
        relations = RelationRepository(connection).list()
        assert relations[0]["source_id"] == dcc_id
        assert relations[0]["target_id"] == rack_id
        assert relations[0]["relation_type"] == "mounted_on"
        assert relations[0]["candidate_id"] == candidates[0]["id"]
