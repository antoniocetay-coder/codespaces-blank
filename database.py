import sqlite3
import json
import uuid

from datetime import datetime, timezone

from config import *

# ==============================================================================
# CONNECTION
# ==============================================================================

def get_conn():

    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    return conn

# ==============================================================================
# INIT DATABASE
# ==============================================================================

def init_db():

    conn = get_conn()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS erros_por_sistema (
            sistema TEXT PRIMARY KEY,
            total INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS tag_stats (
            tag TEXT PRIMARY KEY,
            correct INTEGER DEFAULT 0,
            total INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS flashcards (

            id TEXT PRIMARY KEY,

            front TEXT NOT NULL,
            back TEXT NOT NULL,

            next_review TEXT NOT NULL,

            interval INTEGER DEFAULT 1,
            ease_factor REAL DEFAULT 2.5,

            repetitions INTEGER DEFAULT 0,
            lapses INTEGER DEFAULT 0,

            sistema TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS historico (

            id TEXT PRIMARY KEY,

            questao TEXT NOT NULL,
            timestamp TEXT NOT NULL,

            sistema TEXT,
            acertou INTEGER
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS questions (

            id TEXT PRIMARY KEY,

            sistema TEXT,
            dificuldade TEXT,

            question_json TEXT,

            correct_answer TEXT,

            answered_correctly INTEGER,

            tags TEXT,

            created_at TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS card_reviews (

            id TEXT PRIMARY KEY,

            card_id TEXT,
            quality INTEGER,

            old_interval INTEGER,
            new_interval INTEGER,

            review_date TEXT
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_flashcards_review
        ON flashcards(next_review)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_historico_timestamp
        ON historico(timestamp)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_historico_sistema
        ON historico(sistema)
    """)

    for s in SISTEMAS_DISPONIVEIS:

        conn.execute("""
            INSERT OR IGNORE INTO erros_por_sistema
            (sistema, total)
            VALUES (?, 0)
        """, (s,))

    conn.commit()

# ==============================================================================
# QUESTIONS
# ==============================================================================

def salvar_questao(
    sistema,
    dificuldade,
    questao,
    acertou
):

    conn = get_conn()

    conn.execute("""
        INSERT INTO questions
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (

        str(uuid.uuid4()),

        sistema,
        dificuldade,

        json.dumps(
            questao,
            ensure_ascii=False
        ),

        questao["correct"],

        int(acertou),

        json.dumps(
            questao["content_tags"]
        ),

        datetime.now(
            timezone.utc
        ).isoformat()
    ))

    conn.commit()

def get_questions():

    conn = get_conn()

    rows = conn.execute("""
        SELECT *
        FROM questions
        ORDER BY created_at DESC
    """).fetchall()

    return [dict(r) for r in rows]
    