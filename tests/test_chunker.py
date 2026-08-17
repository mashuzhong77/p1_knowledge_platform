"""文档切片：按最大长度切分并保留重叠；Markdown 按一级标题分节；长切短合。"""

from app.knowledge.chunker import chunk_text, parse_markdown_units, refine_units


def test_chunk_text_respects_max_chars_and_keeps_full_text():
    text = "字" * 1000
    chunks = chunk_text(text, max_chars=300, overlap=0)
    assert all(len(c) <= 300 for c in chunks)
    assert len(chunks) > 1
    assert "".join(chunks) == text


def test_chunk_text_keeps_overlap_between_neighbors():
    text = "字" * 500
    chunks = chunk_text(text, max_chars=300, overlap=50)
    assert chunks[1].startswith(chunks[0][-50:])


def test_parse_markdown_units_splits_by_top_level_headings():
    md = "# 标题一\n内容一\n## 子节\n内容二\n# 标题二\n内容三"
    units = parse_markdown_units(md)
    assert len(units) == 2
    assert units[0]["title"] == "标题一"
    assert "内容二" in units[0]["content"]
    assert units[1]["title"] == "标题二"
    assert "内容三" in units[1]["content"]


def test_refine_units_splits_long_and_merges_short():
    long_unit = {"title": "长章节", "content": "字" * 1200}
    short_a = {"title": "短节", "content": "短内容一"}
    short_b = {"title": "短节", "content": "短内容二"}
    refined = refine_units([long_unit, short_a, short_b], max_chars=800, min_chars=200)

    titles = [u["title"] for u in refined]
    assert any(t.startswith("长章节-") for t in titles)
    assert all(len(u["content"]) <= 800 for u in refined)
    # 两个同标题短节应被合并
    merged_short = [u for u in refined if u["title"] == "短节"]
    assert len(merged_short) == 1
    assert "短内容一" in merged_short[0]["content"]
    assert "短内容二" in merged_short[0]["content"]


def test_refine_units_skips_empty_content():
    refined = refine_units([{"title": "空", "content": "   "}])
    assert refined == []
