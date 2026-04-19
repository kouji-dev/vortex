from ai_portal.knowledge_base.workers.ingest.chunking import semantic_chunks, file_type_for_suffix


def test_prose_produces_chunks_with_metadata():
    paragraphs = [
        f"Topic {i} discusses a completely different subject with unique vocabulary. "
        f"This paragraph covers area number {i} in depth with specific details. "
        f"The conclusion of section {i} wraps up with a summary of findings. "
        for i in range(60)
    ]
    text = " ".join(paragraphs)
    chunks = semantic_chunks(text, "prose", "test.txt", 1)
    assert len(chunks) > 1
    for content, meta in chunks:
        assert len(content) > 0
        assert meta["file_type"] == "prose"
        assert meta["source"] == "test.txt"


def test_markdown_produces_chunks():
    text = "# Section One\nContent one paragraph.\n\n## Section Two\nContent two paragraph.\n\n## Section Three\nContent three paragraph.\n"
    chunks = semantic_chunks(text, "markdown", "doc.md", 1)
    assert len(chunks) >= 1
    contents = [c for c, _ in chunks]
    assert any("Section" in c or "Content" in c for c in contents)


def test_chunk_metadata_has_required_fields():
    text = "Some prose text with enough words to form a chunk. " * 20
    chunks = semantic_chunks(text, "prose", "test.txt", 1)
    for content, meta in chunks:
        assert "source" in meta
        assert "file_type" in meta
        assert "char_start" in meta
        assert "char_end" in meta
        assert "section" in meta
        assert isinstance(meta["char_start"], int)
        assert isinstance(meta["char_end"], int)


def test_empty_text_returns_empty():
    chunks = semantic_chunks("", "prose", "test.txt", 1)
    assert chunks == []


def test_code_file_type_uses_code_chunker():
    code = "def foo():\n    return 1\n\ndef bar():\n    return 2\n" * 10
    chunks = semantic_chunks(code, "code", "main.py", 1)
    assert len(chunks) >= 1
    for _, meta in chunks:
        assert meta["file_type"] == "code"


def test_file_type_for_suffix():
    assert file_type_for_suffix(".pdf") == "pdf"
    assert file_type_for_suffix(".md") == "markdown"
    assert file_type_for_suffix(".py") == "code"
    assert file_type_for_suffix(".txt") == "prose"
    assert file_type_for_suffix(".html") == "prose"
    assert file_type_for_suffix(".htm") == "prose"
    assert file_type_for_suffix(".ts") == "code"
    assert file_type_for_suffix(".go") == "code"


def test_page_propagated_into_meta():
    text = "Sentence one. Sentence two. Sentence three."
    chunks = semantic_chunks(text, "prose", "doc.txt", 7)
    assert len(chunks) >= 1
    for _, meta in chunks:
        assert meta["page"] == 7


def test_large_prose_produces_multiple_chunks():
    text = "This is a moderately long sentence that has enough content. " * 200
    chunks = semantic_chunks(text, "prose", "big.txt", 1)
    assert len(chunks) > 1


def test_section_label_extracted():
    text = "# My Heading\nSome body text.\n\n## Another\nMore text."
    chunks = semantic_chunks(text, "markdown", "doc.md", 1)
    sections = [meta["section"] for _, meta in chunks]
    assert any(s for s in sections)
