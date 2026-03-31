from ai_portal.workers.ingest.chunking import semantic_chunks, file_type_for_suffix


def test_prose_chunks_respect_sentence_boundaries():
    text = "First sentence here. Second sentence here. Third sentence. " * 50
    chunks = semantic_chunks(text, "prose", "test.txt", 1)
    assert len(chunks) > 1
    for content, meta in chunks:
        assert len(content) > 0
        assert meta["file_type"] == "prose"
        assert meta["source"] == "test.txt"


def test_markdown_splits_on_headings():
    text = "# Section One\nContent one.\n\n## Section Two\nContent two.\n\n## Section Three\nContent three.\n"
    chunks = semantic_chunks(text, "markdown", "doc.md", 1)
    assert len(chunks) >= 2
    contents = [c for c, _ in chunks]
    assert any("Section One" in c or "Section Two" in c for c in contents)


def test_chunk_metadata_has_required_fields():
    text = "Some prose text. " * 20
    chunks = semantic_chunks(text, "prose", "test.txt", 1)
    for content, meta in chunks:
        assert "source" in meta
        assert "file_type" in meta
        assert "char_start" in meta
        assert "char_end" in meta
        assert "section" in meta


def test_empty_text_returns_empty():
    chunks = semantic_chunks("", "prose", "test.txt", 1)
    assert chunks == []


def test_code_file_type_accepted():
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


def test_page_propagated_into_meta():
    text = "Sentence one. Sentence two. Sentence three."
    chunks = semantic_chunks(text, "prose", "doc.txt", 7)
    assert len(chunks) >= 1
    for _, meta in chunks:
        assert meta["page"] == 7


def test_overlap_carries_last_two_sentences():
    # Build text large enough to force a flush so we can inspect overlap
    # Use long sentences to force chunking. 2000 chars per chunk.
    long_sent = "A" * 300
    # 8 sentences of 300 chars each = 2400 chars total, should produce 2+ chunks
    sentences = [f"Sentence {i} {'x' * 290}." for i in range(10)]
    text = " ".join(sentences)
    chunks = semantic_chunks(text, "prose", "file.txt", 1)
    assert len(chunks) >= 2
    # The second chunk should start with the last 2 sentences of the first chunk
    first_content = chunks[0][0]
    second_content = chunks[1][0]
    # Split first chunk on ". " to get its sentences
    first_sentences = [s.strip() for s in first_content.split(". ") if s.strip()]
    if len(first_sentences) >= 2:
        last_two = first_sentences[-2:]
        # Both last two sentences should appear in the start of the second chunk
        for sent in last_two:
            assert sent[:30] in second_content


def test_markdown_h3_not_split_boundary():
    # h3 headings (###) should NOT be treated as split points
    text = "# H1 heading\nContent under h1.\n\n### H3 heading\nContent under h3.\n\n## H2 heading\nContent under h2.\n"
    chunks = semantic_chunks(text, "markdown", "doc.md", 1)
    # H1 and H2 are split boundaries, H3 is not — it gets absorbed into the section body
    headings = [meta["section"] for _, meta in chunks]
    assert "H1 heading" in headings or any("H1 heading" in c for c, _ in chunks)
    assert "H2 heading" in headings or any("H2 heading" in c for c, _ in chunks)
    # H3 should NOT appear as its own section heading
    assert "H3 heading" not in headings
