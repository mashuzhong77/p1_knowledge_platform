"""SQLite 数据库：建表与连接管理。"""

import sqlite3
from contextlib import contextmanager

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id INTEGER,
    name TEXT NOT NULL,
    leader_id INTEGER,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_name TEXT NOT NULL,
    role_code TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    department_id INTEGER,
    status TEXT DEFAULT 'active',
    must_change_password INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS user_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS role_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    permission_code TEXT NOT NULL,
    permission_type TEXT DEFAULT 'button',
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS knowledge_units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_code TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    summary TEXT DEFAULT '',
    category TEXT DEFAULT '',
    source_file_name TEXT DEFAULT '',
    file_type TEXT DEFAULT '',
    file_size INTEGER DEFAULT 0,
    status TEXT DEFAULT 'draft',
    version_no INTEGER DEFAULT 1,
    parent_id INTEGER,
    security_level TEXT DEFAULT 'internal',
    data_domain TEXT DEFAULT '',
    creator_id INTEGER,
    reviewed_by INTEGER,
    reviewed_at TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS unit_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS qa_access_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT DEFAULT '',
    user_id INTEGER,
    question TEXT,
    answer TEXT,
    recalled_unit_ids_json TEXT DEFAULT '[]',
    authorized_unit_ids_json TEXT DEFAULT '[]',
    unauthorized_unit_ids_json TEXT DEFAULT '[]',
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    response_time_ms INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS faqs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT,
    answer TEXT,
    category TEXT DEFAULT '',
    related_unit_id INTEGER,
    source_type TEXT DEFAULT 'auto_mined',
    status TEXT DEFAULT 'pending_review',
    hit_count INTEGER DEFAULT 0,
    reviewer_id INTEGER,
    reviewed_at TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS knowledge_gaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_pattern TEXT,
    sample_questions_json TEXT DEFAULT '[]',
    ask_count INTEGER DEFAULT 1,
    last_asked_at TEXT,
    status TEXT DEFAULT 'unresolved',
    resolved_unit_id INTEGER,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    resource_type TEXT,
    resource_id TEXT,
    detail_json TEXT DEFAULT '{}',
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS qa_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT DEFAULT '',
    user_id INTEGER,
    question TEXT,
    answer TEXT,
    rating TEXT DEFAULT 'up',
    feedback_type TEXT DEFAULT 'none',
    comment TEXT DEFAULT '',
    created_at TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS unit_fts USING fts5(
    unit_id UNINDEXED,
    title,
    content,
    tokenize='trigram'
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    expires_at REAL NOT NULL,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at);
"""


def get_connection() -> sqlite3.Connection:
    """创建 SQLite 连接（row_factory=Row，WAL 模式，busy_timeout 5s）。"""
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(settings.db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")       # 并发读不阻塞写，写不阻塞读
    conn.execute("PRAGMA busy_timeout = 5000")       # 遇锁等待 5s 而非立即报错
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """初始化全部数据表。"""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn) -> None:
    """为已存在的库补齐 spec 2.9.7 新增列（CREATE TABLE IF NOT EXISTS 不会改已有表）。"""
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(roles)").fetchall()}
    for col in ("created_at", "updated_at"):
        if col not in existing:
            conn.execute(f"ALTER TABLE roles ADD COLUMN {col} TEXT")
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(departments)").fetchall()}
    if "updated_at" not in existing:
        conn.execute("ALTER TABLE departments ADD COLUMN updated_at TEXT")
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "must_change_password" not in existing:
        conn.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0")


@contextmanager
def db():
    """带提交/回滚/关闭的数据库上下文。"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
