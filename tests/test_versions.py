"""知识单元版本：发布后更新生成新草稿版本；回滚复制目标版本内容。"""

from app.database import get_connection
from app.knowledge.crud import (
    archive_unit,
    create_unit,
    list_versions,
    publish_unit,
    rollback_unit,
    update_unit_content,
)


def test_update_published_creates_new_draft_version(db):
    with get_connection() as conn:
        unit_id = create_unit(conn, title="规范A", content="v1 内容", creator_id=1)
        publish_unit(conn, unit_id, reviewer_id=1)
        new_id = update_unit_content(conn, unit_id, "v2 内容")

    assert new_id != unit_id
    with get_connection() as conn:
        versions = list_versions(conn, unit_id)
        assert len(versions) == 2
        assert versions[0]["id"] == unit_id
        assert versions[1]["id"] == new_id
        assert versions[1]["status"] == "draft"


def test_rollback_copies_target_version_content(db):
    with get_connection() as conn:
        v1 = create_unit(conn, title="规范B", content="原始内容", creator_id=1)
        publish_unit(conn, v1, reviewer_id=1)
        v2 = update_unit_content(conn, v1, "修改后的内容")
        v3 = rollback_unit(conn, v2, target_version_id=v1, user_id=1)

    with get_connection() as conn:
        row = conn.execute("SELECT content, status, version_no FROM knowledge_units WHERE id=?", (v3,)).fetchone()
        assert row["content"] == "原始内容"
        assert row["status"] == "draft"
        assert row["version_no"] == 3


def test_archive_changes_status(db):
    with get_connection() as conn:
        unit_id = create_unit(conn, title="规范C", content="内容", creator_id=1)
        publish_unit(conn, unit_id, reviewer_id=1)
        archive_unit(conn, unit_id)
        row = conn.execute("SELECT status FROM knowledge_units WHERE id=?", (unit_id,)).fetchone()
        assert row["status"] == "archived"
