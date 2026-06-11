import sqlite3
import streamlit as st
from enum import Enum
from datetime import datetime, timezone
from config import SISTEMAS_DISPONIVEIS

DB_PATH = "usmle_data.db"


class ItemType(Enum):
    FLASHCARD = "flashcard"
    QUESTION = "question"


@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db():
    conn = get_conn()

    conn.execute(
        "CREATE TABLE IF NOT EXISTS erros_por_sistema "
        "(sistema TEXT PRIMARY KEY, total INTEGER DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tag_stats "
        "(tag TEXT PRIMARY KEY, correct INTEGER DEFAULT 0, total INTEGER DEFAULT 0)"
    )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS flashcards (
            id TEXT PRIMARY KEY, front TEXT NOT NULL, back TEXT NOT NULL, sistema TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS srs_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id TEXT NOT NULL, object_type TEXT NOT NULL,
            stability REAL DEFAULT 0.0, difficulty REAL DEFAULT 0.0,
            due TEXT, repetitions INTEGER DEFAULT 0, lapses INTEGER DEFAULT 0,
            last_review TEXT,
            UNIQUE(object_id, object_type)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id TEXT PRIMARY KEY, sistema TEXT, dificuldade TEXT,
            question_json TEXT, correct_answer TEXT,
            answered_correctly INTEGER, created_at TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS item_tags (
            object_id TEXT NOT NULL, object_type TEXT NOT NULL,
            tag TEXT NOT NULL,
            UNIQUE(object_id, object_type, tag)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS confusion_pairs (
            tag_correct TEXT NOT NULL,
            tag_confused TEXT NOT NULL,
            count INTEGER DEFAULT 1,
            last_seen TEXT NOT NULL,
            PRIMARY KEY (tag_correct, tag_confused)
        )
    """)

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_srs_state_obj "
        "ON srs_state(object_id, object_type)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_srs_state_due ON srs_state(due)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_item_tags_tag ON item_tags(tag)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_item_tags_obj "
        "ON item_tags(object_id, object_type)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_confusion_pairs ON confusion_pairs(tag_correct)"
    )

    try:
        conn.execute("ALTER TABLE questions ADD COLUMN time_taken_seconds INTEGER")
        conn.execute("ALTER TABLE questions ADD COLUMN confidence_level TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute(
            "ALTER TABLE tag_stats ADD COLUMN mastery_prob REAL DEFAULT 0.15"
        )
    except sqlite3.OperationalError:
        pass

    for s in SISTEMAS_DISPONIVEIS:
        conn.execute(
            "INSERT OR IGNORE INTO erros_por_sistema (sistema, total) VALUES (?, 0)",
            (s,),
        )

    conn.commit()
