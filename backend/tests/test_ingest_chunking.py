from ai_portal.workers.ingest.chunking import semantic_chunks, file_type_for_suffix


def test_prose_chunks_respect_sentence_boundaries():
    text = "First sentence here. Second sentence here. Third sentence. " * 50
    chunks = semantic_chunks(text, file_type="prose", filename="test.txt")
    assert len(chunks) > 1
    for content, meta in chunks:
        assert len(content) > 0
        assert meta["file_type"] == "prose"
        assert meta["source"] == "test.txt"


def test_markdown_splits_on_headings():
    text = "# Section One\nContent one.\n\n## Section Two\nContent two.\n\n## Section Three\nContent three.\n"
    chunks = semantic_chunks(text, file_type="markdown", filename="doc.md")
    assert len(chunks) >= 2
    contents = [c for c, _ in chunks]
    assert any("Section One" in c or "Section Two" in c for c in contents)


def test_chunk_metadata_has_required_fields():
    text = "Some prose text. " * 20
    chunks = semantic_chunks(text, file_type="prose", filename="test.txt")
    for content, meta in chunks:
        assert "source" in meta
        assert "file_type" in meta
        assert "char_start" in meta
        assert "char_end" in meta


def test_empty_text_returns_empty():
    chunks = semantic_chunks("", file_type="prose", filename="test.txt")
    assert chunks == []


def test_code_file_type_accepted():
    code = "def foo():\n    return 1\n\ndef bar():\n    return 2\n" * 10
    chunks = semantic_chunks(code, file_type="code", filename="main.py")
    assert len(chunks) >= 1
    for _, meta in chunks:
        assert meta["file_type"] == "code"


def test_file_type_for_suffix():
    assert file_type_for_suffix(".pdf") == "pdf"
    assert file_type_for_suffix(".md") == "markdown"
    assert file_type_for_suffix(".py") == "code"
    assert file_type_for_suffix(".txt") == "prose"
    assert file_type_for_suffix(".html") == "html"
