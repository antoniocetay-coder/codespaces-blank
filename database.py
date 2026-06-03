import sqlite3
import json
import uuid
import streamlit as st
from enum import Enum
from datetime import datetime, timezone, timedelta
from config import *

class ItemType(Enum):
    FLASHCARD = "flashcard"
    QUESTION  = "question"

@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    conn = get_conn()

    conn.execute("CREATE TABLE IF NOT EXISTS erros_por_sistema (sistema TEXT PRIMARY KEY, total INTEGER DEFAULT 0)")
    conn.execute("CREATE TABLE IF NOT EXISTS tag_stats (tag TEXT PRIMARY KEY, correct INTEGER DEFAULT 0, total INTEGER DEFAULT 0)")

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
            due TEXT, repetitions INTEGER DEFAULT 0, lapses INTEGER DEFAULT 0, last_review TEXT,
            UNIQUE(object_id, object_type)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id TEXT PRIMARY KEY, sistema TEXT, dificuldade TEXT,
            question_json TEXT, correct_answer TEXT, answered_correctly INTEGER, created_at TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS item_tags (
            object_id TEXT NOT NULL, object_type TEXT NOT NULL, tag TEXT NOT NULL, UNIQUE(object_id, object_type, tag)
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

    conn.execute("CREATE INDEX IF NOT EXISTS idx_srs_state_obj ON srs_state(object_id, object_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_srs_state_due ON srs_state(due)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_item_tags_tag ON item_tags(tag)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_item_tags_obj ON item_tags(object_id, object_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_confusion_pairs ON confusion_pairs(tag_correct)")

    # Atualização dinâmica do esquema (Metacognição, Tempo e BKT)
    try:
        conn.execute("ALTER TABLE questions ADD COLUMN time_taken_seconds INTEGER")
        conn.execute("ALTER TABLE questions ADD COLUMN confidence_level TEXT")
    except sqlite3.OperationalError:
        pass # As colunas já existem

    try:
        # Coluna nova para armazenar o Teorema de Bayes
        conn.execute("ALTER TABLE tag_stats ADD COLUMN mastery_prob REAL DEFAULT 0.15")
    except sqlite3.OperationalError:
        pass # A coluna já existe

    for s in SISTEMAS_DISPONIVEIS:
        conn.execute("INSERT OR IGNORE INTO erros_por_sistema (sistema, total) VALUES (?, 0)", (s,))

    conn.commit()


def salvar_questao(sistema, dificuldade, questao, acertou, tags, status="answered"):
    conn = get_conn()
    q_id = str(uuid.uuid4())
    ans_val = None if status == "pending" else int(acertou)

    conn.execute("""
        INSERT INTO questions (id, sistema, dificuldade, question_json, correct_answer, answered_correctly, created_at) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        q_id,
        sistema,
        dificuldade,
        json.dumps(questao, ensure_ascii=False),
        questao["correct"],
        ans_val,
        datetime.now(timezone.utc).isoformat()
    ))

    for tag in tags:
        conn.execute("INSERT INTO item_tags (object_id, object_type, tag) VALUES (?, ?, ?)", (q_id, ItemType.QUESTION.value, tag))
    conn.commit()


def marcar_questao_respondida(q_id, acertou, time_taken=None, confidence=None):
    conn = get_conn()
    conn.execute("""
        UPDATE questions 
        SET answered_correctly = ?, time_taken_seconds = ?, confidence_level = ?
        WHERE id = ?
    """, (int(acertou), time_taken, confidence, q_id))
    conn.commit()


def get_questions():
    conn = get_conn()
    rows = conn.execute("""
        SELECT q.*, GROUP_CONCAT(t.tag, '|') as tag_list
        FROM questions q
        LEFT JOIN item_tags t ON q.id = t.object_id AND t.object_type = 'question'
        WHERE q.answered_correctly IS NOT NULL
        GROUP BY q.id
        ORDER BY q.created_at DESC
    """).fetchall()
    return [dict(r) for r in rows]


def get_pending_questions():
    conn = get_conn()
    rows = conn.execute("""
        SELECT q.*, GROUP_CONCAT(t.tag, '|') as tag_list
        FROM questions q
        LEFT JOIN item_tags t ON q.id = t.object_id AND t.object_type = 'question'
        WHERE q.answered_correctly IS NULL
        GROUP BY q.id
        ORDER BY q.created_at ASC
    """).fetchall()
    return [dict(r) for r in rows]


def salvar_flashcard_db(front, back, sistema, tags):
    conn = get_conn()
    f_id = str(uuid.uuid4())
    conn.execute("INSERT INTO flashcards (id, front, back, sistema) VALUES (?, ?, ?, ?)", (f_id, front, back, sistema))

    for tag in tags:
        conn.execute("INSERT INTO item_tags (object_id, object_type, tag) VALUES (?, ?, ?)", (f_id, ItemType.FLASHCARD.value, tag))
    conn.commit()


def get_cards_hoje():
    conn = get_conn()
    hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    rows = conn.execute("""
        SELECT f.*, 
               COALESCE(s.stability, 0) as stability, 
               COALESCE(s.difficulty, 0) as difficulty, 
               s.due, 
               COALESCE(s.repetitions, 0) as repetitions, 
               COALESCE(s.lapses, 0) as lapses, 
               s.last_review
        FROM flashcards f
        LEFT JOIN srs_state s ON f.id = s.object_id AND s.object_type = 'flashcard'
        WHERE s.due IS NULL OR s.due <= ?
    """, (hoje,)).fetchall()
    return [dict(r) for r in rows]


def get_flashcards_by_tags(tags):
    if not tags:
        return []
    conn = get_conn()
    placeholders = ",".join(["?"] * len(tags))
    query = f"""
        SELECT DISTINCT f.front, f.back
        FROM flashcards f
        JOIN item_tags t ON f.id = t.object_id AND t.object_type = 'flashcard'
        WHERE t.tag IN ({placeholders})
    """
    rows = conn.execute(query, tags).fetchall()
    return [{"front": r["front"], "back": r["back"]} for r in rows]


def registrar_confusao(tag_correct, tag_confused):
    conn = get_conn()
    agora = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO confusion_pairs (tag_correct, tag_confused, count, last_seen)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(tag_correct, tag_confused)
        DO UPDATE SET count = count + 1, last_seen = excluded.last_seen
    """, (tag_correct, tag_confused, agora))
    conn.commit()


def get_tags_em_cooldown(horas=48):
    conn = get_conn()
    corte_tempo = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
    rows = conn.execute("""
        SELECT DISTINCT t.tag
        FROM item_tags t
        JOIN questions q ON t.object_id = q.id
        WHERE q.created_at >= ?
    """, (corte_tempo,)).fetchall()
    return [r["tag"] for r in rows]


def registrar_cooldown_tags(tags):
    """
    O cooldown já é controlado implicitamente via created_at das questões
    em get_tags_em_cooldown(). Esta função existe por compatibilidade de interface
    e pode ser usada futuramente para um registro explícito de cooldown, se necessário.
    """
    pass


def get_top_confounders(tag_correct, limit=3):
    conn = get_conn()
    rows = conn.execute("""
        SELECT tag_confused 
        FROM confusion_pairs 
        WHERE tag_correct = ? 
        ORDER BY count DESC 
        LIMIT ?
    """, (tag_correct, limit)).fetchall()
    return [r["tag_confused"] for r in rows]


def get_system_stats():
    conn = get_conn()
    rows = conn.execute("""
        SELECT sistema,
               SUM(CASE WHEN answered_correctly = 1 THEN 1 ELSE 0 END) as acertos,
               COUNT(*) as total
        FROM questions
        WHERE answered_correctly IS NOT NULL
        GROUP BY sistema
    """).fetchall()
    return [dict(r) for r in rows]


def get_metacognition_stats():
    conn = get_conn()
    rows = conn.execute("""
        SELECT confidence_level, answered_correctly, COUNT(*) as qtd
        FROM questions
        WHERE confidence_level IS NOT NULL
        GROUP BY confidence_level, answered_correctly
    """).fetchall()
    return [dict(r) for r in rows]


def get_time_stats():
    conn = get_conn()
    rows = conn.execute("""
        SELECT sistema, answered_correctly, AVG(time_taken_seconds) as avg_time
        FROM questions
        WHERE time_taken_seconds IS NOT NULL
        GROUP BY sistema, answered_correctly
    """).fetchall()
    return [dict(r) for r in rows]


def get_fsrs_forecast():
    conn = get_conn()
    rows = conn.execute("""
        SELECT due, COUNT(*) as qtd
        FROM srs_state
        WHERE object_type = 'flashcard' AND due IS NOT NULL
        GROUP BY due
        ORDER BY due ASC
        LIMIT 14
    """).fetchall()
    return [dict(r) for r in rows]


def get_global_confusions(limit=10):
    conn = get_conn()
    rows = conn.execute("""
        SELECT tag_correct, tag_confused, count
        FROM confusion_pairs
        ORDER BY count DESC
        LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]
