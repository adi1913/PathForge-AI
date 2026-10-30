import pytest

from app.rag.chunking.chunker import StructuralChunker
from app.rag.parsers.factory import get_parser


def test_chunk_size_is_respected():
    text = "word " * 500
    doc = get_parser("text").parse(text)
    chunker = StructuralChunker(chunk_size=200, chunk_overlap=40, min_chunk_size=20)
    chunks = chunker.chunk(doc)
    assert all(len(c.content) <= 200 for c in chunks)
    assert len(chunks) > 1


def test_chunk_overlap_produces_shared_content_between_consecutive_chunks():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa " * 10
    doc = get_parser("text").parse(text)
    chunker = StructuralChunker(chunk_size=100, chunk_overlap=30, min_chunk_size=10)
    chunks = chunker.chunk(doc)
    assert len(chunks) > 1
    tail = chunks[0].content[-15:]
    assert tail in chunks[1].content


def test_small_document_produces_single_chunk():
    doc = get_parser("text").parse("Just one short paragraph.")
    chunker = StructuralChunker(chunk_size=1000, chunk_overlap=100, min_chunk_size=10)
    chunks = chunker.chunk(doc)
    assert len(chunks) == 1


def test_code_block_stays_intact_when_it_fits():
    md = "# T\n\n```python\nx = 1\ny = 2\n```\n"
    doc = get_parser("markdown").parse(md)
    chunker = StructuralChunker(chunk_size=500, chunk_overlap=50, min_chunk_size=10)
    chunks = chunker.chunk(doc)
    code_chunks = [c for c in chunks if c.content_type == "code"]
    assert len(code_chunks) == 1
    assert code_chunks[0].content == "x = 1\ny = 2"


def test_oversized_code_block_is_split_on_line_boundaries_only():
    long_code = "\n".join(f"line_{i} = {i}" for i in range(100))
    md = f"# T\n\n```python\n{long_code}\n```\n"
    doc = get_parser("markdown").parse(md)
    chunker = StructuralChunker(chunk_size=200, chunk_overlap=30, min_chunk_size=10)
    chunks = chunker.chunk(doc)
    code_chunks = [c for c in chunks if c.content_type == "code"]
    assert len(code_chunks) > 1
    for c in code_chunks:
        for line in c.content.split("\n"):
            assert line == "" or line.startswith("line_")  # never a mid-line cut


def test_different_sections_are_not_merged_into_one_chunk():
    md = "# T\n\n## A\n\nshort a\n\n## B\n\nshort b\n"
    doc = get_parser("markdown").parse(md)
    chunker = StructuralChunker(chunk_size=1000, chunk_overlap=50, min_chunk_size=1)
    chunks = chunker.chunk(doc)
    paths = [c.heading_path for c in chunks]
    assert ["T", "A"] in paths
    assert ["T", "B"] in paths
    assert len(chunks) == 2  # not merged into one


def test_chunk_metadata_preserved():
    md = "# Doc\n\n## Sec\n\nSome content here."
    doc = get_parser("markdown").parse(md)
    chunker = StructuralChunker(chunk_size=500, chunk_overlap=50, min_chunk_size=10)
    chunks = chunker.chunk(doc)
    assert chunks[0].heading_path == ["Doc", "Sec"]
    assert chunks[0].chunk_index == 0


def test_overlap_must_be_smaller_than_chunk_size():
    with pytest.raises(ValueError):
        StructuralChunker(chunk_size=100, chunk_overlap=100, min_chunk_size=10)
