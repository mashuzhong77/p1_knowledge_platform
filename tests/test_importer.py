"""导入：内容哈希等价去重（文件名 + 内容一致视为重复）。"""

from app.config import settings
from app.knowledge.importer import import_text


def test_import_text_duplicate_by_content(db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "vector_dir", tmp_path / "vec")
    first = import_text("规范A", "# 章节\n内容", 1, source_file_name="a.md")
    assert first["imported"] >= 1
    second = import_text("规范A", "# 章节\n内容", 1, source_file_name="a.md")
    assert second.get("duplicated") is True
    assert second["imported"] == 0


def test_import_text_same_content_different_file_not_duplicate(db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "vector_dir", tmp_path / "vec2")
    first = import_text("规范A", "内容", 1, source_file_name="a.md")
    second = import_text("规范A", "内容", 1, source_file_name="b.md")
    assert first["imported"] >= 1
    assert second.get("duplicated") is not True
