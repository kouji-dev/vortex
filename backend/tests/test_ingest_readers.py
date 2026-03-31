import pytest
from pathlib import Path
from ai_portal.workers.ingest.readers import stream_text_pages


def test_stream_txt_yields_tuples(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello\nworld\n", encoding="utf-8")
    pages = list(stream_text_pages(f, ".txt"))
    assert len(pages) >= 1
    # Each item must be a (text, page_number) tuple
    for text, page_num in pages:
        assert isinstance(text, str)
        assert isinstance(page_num, int)
    combined = "".join(t for t, _ in pages)
    assert "hello" in combined
    assert "world" in combined


def test_stream_txt_chunk_indices_are_sequential(tmp_path):
    f = tmp_path / "big.txt"
    # Write content larger than 4KB to get multiple chunks
    f.write_text(("a" * 100 + "\n") * 50, encoding="utf-8")
    pages = list(stream_text_pages(f, ".txt"))
    indices = [page_num for _, page_num in pages]
    assert indices == list(range(len(indices)))


def test_stream_md_yields_content(tmp_path):
    f = tmp_path / "test.md"
    f.write_text("# Heading\nSome text\n## Section\nMore text\n", encoding="utf-8")
    pages = list(stream_text_pages(f, ".md"))
    combined = "".join(t for t, _ in pages)
    assert "Heading" in combined
    assert "More text" in combined


def test_unsupported_type_raises(tmp_path):
    f = tmp_path / "test.xyz"
    f.write_bytes(b"data")
    with pytest.raises(ValueError, match="unsupported_type"):
        list(stream_text_pages(f, ".xyz"))


def test_stream_yaml_supported(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("key: value\nother: 123\n", encoding="utf-8")
    pages = list(stream_text_pages(f, ".yaml"))
    assert len(pages) >= 1
    combined = "".join(t for t, _ in pages)
    assert "key" in combined


def test_stream_yml_supported(tmp_path):
    f = tmp_path / "config.yml"
    f.write_text("key: value\n", encoding="utf-8")
    pages = list(stream_text_pages(f, ".yml"))
    assert len(pages) >= 1


def test_stream_json_supported(tmp_path):
    f = tmp_path / "data.json"
    f.write_text('{"key": "value"}\n', encoding="utf-8")
    pages = list(stream_text_pages(f, ".json"))
    assert len(pages) >= 1
    combined = "".join(t for t, _ in pages)
    assert "key" in combined


def test_stream_toml_supported(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text("[section]\nkey = \"value\"\n", encoding="utf-8")
    pages = list(stream_text_pages(f, ".toml"))
    assert len(pages) >= 1
    combined = "".join(t for t, _ in pages)
    assert "section" in combined


def test_stream_html_yields_tuples(tmp_path):
    f = tmp_path / "page.html"
    f.write_text("<html><body><p>Hello world</p></body></html>", encoding="utf-8")
    pages = list(stream_text_pages(f, ".html"))
    assert len(pages) >= 1
    for text, page_num in pages:
        assert isinstance(text, str)
        assert isinstance(page_num, int)
    combined = "".join(t for t, _ in pages)
    assert "Hello world" in combined


def test_stream_html_multiple_chunks_sequential_indices(tmp_path):
    f = tmp_path / "big.html"
    # Create content larger than 4KB after tag stripping
    inner = ("word " * 200 + "\n") * 5  # ~6KB of text
    f.write_text(f"<html><body><p>{inner}</p></body></html>", encoding="utf-8")
    pages = list(stream_text_pages(f, ".html"))
    assert len(pages) > 1, "Expected multiple chunks for large HTML content"
    indices = [page_num for _, page_num in pages]
    assert indices == list(range(len(indices)))


def test_stream_pdf_1based_page_numbers(tmp_path):
    """PDF page numbers must be 1-based."""
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter
    import io

    writer = PdfWriter()
    for i in range(3):
        page = writer.add_blank_page(width=200, height=200)

    # Write PDF to a temp file - blank pages have no extractable text,
    # so we test using a mock instead.
    # Use a simple approach: verify the indexing logic via a mock
    from unittest.mock import MagicMock, patch

    mock_page1 = MagicMock()
    mock_page1.extract_text.return_value = "Page one content"
    mock_page2 = MagicMock()
    mock_page2.extract_text.return_value = "Page two content"
    mock_page3 = MagicMock()
    mock_page3.extract_text.return_value = "Page three content"

    mock_reader = MagicMock()
    mock_reader.pages = [mock_page1, mock_page2, mock_page3]

    f = tmp_path / "test.pdf"
    f.write_bytes(b"%PDF-1.4 fake")

    with patch("pypdf.PdfReader", return_value=mock_reader):
        pages = list(stream_text_pages(f, ".pdf"))

    assert len(pages) == 3
    texts = [t for t, _ in pages]
    nums = [n for _, n in pages]
    assert nums == [1, 2, 3], f"Expected 1-based page numbers, got {nums}"
    assert "Page one content" in texts[0]
    assert "Page three content" in texts[2]
