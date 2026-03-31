from pathlib import Path
from ai_portal.workers.ingest.readers import stream_text_pages


def test_stream_txt_yields_lines(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello\nworld\n", encoding="utf-8")
    pages = list(stream_text_pages(f))
    assert len(pages) >= 1
    combined = "\n".join(pages)
    assert "hello" in combined
    assert "world" in combined


def test_stream_md_yields_content(tmp_path):
    f = tmp_path / "test.md"
    f.write_text("# Heading\nSome text\n## Section\nMore text\n", encoding="utf-8")
    pages = list(stream_text_pages(f))
    combined = "\n".join(pages)
    assert "Heading" in combined
    assert "More text" in combined


def test_unsupported_type_raises(tmp_path):
    f = tmp_path / "test.xyz"
    f.write_bytes(b"data")
    import pytest
    with pytest.raises(ValueError, match="unsupported_type"):
        list(stream_text_pages(f))
