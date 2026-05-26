import sqlite3
import json
import uuid
from enum import Enum
from datetime import datetime, timezone
from config import *

class ItemType(Enum):
    FLASHCARD = "flashcard"
    QUESTION  = "question"

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    c
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

    # 1. TABELA APENAS DE CONTEÚDO (Flashcards)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS flashcards (
            id TEXT PRIMARY KEY,
            front TEXT NOT NULL,
            back TEXT NOT NULL,
            sistema TEXT
        )
    """)

    # 2. TABELA UNIVERSAL DE AGENDAMENTO (srs_state)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS srs_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id TEXT NOT NULL,
            object_type TEXT NOT NULL,
            stability REAL DEFAULT 0.0,
            difficulty REAL DEFAULT 0.0,
            due TEXT,
            repetitions INTEGER DEFAULT 0,
            lapses INTEGER DEFAULT 0,
            last_review TEXT,
            UNIQUE(object_id, object_type)
        )
    """)

    # 3. TABELA DE QUESTÕES (Sem a coluna de tags)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id TEXT PRIMARY KEY,
            sistema TEXT,
            dificuldade TEXT,
            question_json TEXT,
            correct_answer TEXT,
            answered_correctly INTEGER,
            created_at TEXT
        )
    """)

    # 4. NOVA TABELA DE TAGS (Separada e Indexada)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS item_tags (
            object_id TEXT NOT NULL,
            object_type TEXT NOT NULL,
            tag TEXT NOT NULL,
            UNIQUE(object_id, object_type, tag)
        )
    """)

    # Índices para o SRS
    conn.execute("CREATE INDEX IF NOT EXISTS idx_srs_state_obj ON srs_state(object_id, object_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_srs_state_due ON srs_state(due)")

    # Índices para as Tags (Busca super rápida)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_item_tags_tag ON item_tags(tag)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_item_tags_obj ON item_tags(object_id, object_type)")

    for s in SISTEMAS_DISPONIVEIS:
        conn.execute("INSERT OR IG