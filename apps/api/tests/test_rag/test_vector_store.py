from app.rag.vector_store.base import VectorPoint
from app.rag.vector_store.qdrant_store import QdrantVectorStore


def _store():
    return QdrantVectorStore(collection_name="test_collection", local_path=None)  # :memory:


async def test_ensure_collection_is_idempotent():
    store = _store()
    await store.ensure_collection(dimension=8)
    await store.ensure_collection(dimension=8)  # must not raise on second call


async def test_upsert_and_search_returns_closest_point():
    store = _store()
    await store.ensure_collection(dimension=4)
    await store.upsert(
        [
            VectorPoint(point_id="11111111-1111-1111-1111-111111111111", vector=[1, 0, 0, 0], payload={"tag": "a"}),
            VectorPoint(point_id="22222222-2222-2222-2222-222222222222", vector=[0, 1, 0, 0], payload={"tag": "b"}),
        ]
    )
    results = await store.search(query_vector=[1, 0, 0, 0], top_k=1)
    assert len(results) == 1
    assert results[0].payload["tag"] == "a"


async def test_upsert_same_id_is_idempotent_not_duplicated():
    store = _store()
    await store.ensure_collection(dimension=4)
    point = VectorPoint(point_id="11111111-1111-1111-1111-111111111111", vector=[1, 0, 0, 0], payload={"v": 1})
    await store.upsert([point])
    await store.upsert([point])
    await store.upsert([point])
    results = await store.search(query_vector=[1, 0, 0, 0], top_k=10)
    assert len(results) == 1


async def test_metadata_filtering():
    store = _store()
    await store.ensure_collection(dimension=4)
    await store.upsert(
        [
            VectorPoint(
                point_id="11111111-1111-1111-1111-111111111111", vector=[1, 0, 0, 0], payload={"skill": "python"}
            ),
            VectorPoint(point_id="22222222-2222-2222-2222-222222222222", vector=[1, 0, 0, 0], payload={"skill": "rag"}),
        ]
    )
    results = await store.search(query_vector=[1, 0, 0, 0], top_k=10, filters={"skill": "rag"})
    assert len(results) == 1
    assert results[0].payload["skill"] == "rag"


async def test_search_respects_top_k_bound():
    store = _store()
    await store.ensure_collection(dimension=4)
    await store.upsert([VectorPoint(point_id=i + 1, vector=[1, 0, 0, 0], payload={"i": i}) for i in range(5)])
    results = await store.search(query_vector=[1, 0, 0, 0], top_k=2)
    assert len(results) == 2


async def test_delete_by_document_id_removes_matching_points_only():
    store = _store()
    await store.ensure_collection(dimension=4)
    await store.upsert(
        [
            VectorPoint(
                point_id="11111111-1111-1111-1111-111111111111",
                vector=[1, 0, 0, 0],
                payload={"document_id": "doc-a"},
            ),
            VectorPoint(
                point_id="22222222-2222-2222-2222-222222222222",
                vector=[1, 0, 0, 0],
                payload={"document_id": "doc-b"},
            ),
        ]
    )
    await store.delete_by_document_id("doc-a")
    results = await store.search(query_vector=[1, 0, 0, 0], top_k=10)
    assert len(results) == 1
    assert results[0].payload["document_id"] == "doc-b"


async def test_has_point_true_and_false():
    store = _store()
    await store.ensure_collection(dimension=4)
    point_id = "11111111-1111-1111-1111-111111111111"
    assert await store.has_point(point_id) is False
    await store.upsert([VectorPoint(point_id=point_id, vector=[1, 0, 0, 0], payload={})])
    assert await store.has_point(point_id) is True


async def test_upsert_empty_list_is_a_no_op():
    store = _store()
    await store.ensure_collection(dimension=4)
    await store.upsert([])  # must not raise
