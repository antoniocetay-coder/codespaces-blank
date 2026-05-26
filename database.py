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
    conn = get_conn()

    conn.execute("CREATE TABLE IF NOT EXISTS erros_por_sistema (sistema TEXT PRIMARY KEY, total INTEGER DEFAULT 0)")
    conn.execute("CREATE TABLE IF NOT EXISTS tag_stats (tag TEXT PRIMARY KEY, correct INTEGER DEFAULT 0, total INTEGER DEFAULT 0)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS flashcards (
            id TEXT PRIMARY KEY,
            front TEXT NOT NULL,
            back TEXT NOT NULL,
            sistema TEXT
        )
    """)

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

    conn.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id TEXT PRIMARY KEY,
            sistema TEXT,
            dificuldade TEXT,
            question_json TEXT,
            correct_answer TEXT,
            answered_correctly INTEGER,
            status TEXT DEFAULT 'answered',
            created_at TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS item_tags (
            object_id TEXT NOT NULL,
            object_type TEXT NOT NULL,
            tag TEXT NOT NULL,
            UNIQUE(object_id, object_type, tag)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS tag_cooldowns (
            tag TEXT PRIMARY KEY,
            last_seen TEXT NOT NULL
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_srs_state_obj ON srs_state(object_id, object_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_srs_state_due ON srs_state(due)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_item_tags_tag ON item_tags(tag)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_item_tags_obj ON item_tags(object_id, object_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status)")

    for s in SISTEMAS_DISPONIVEIS:
        conn.execute("INSERT OR IGNORE INTO erros_por_sistema (sistema, total) VALUES (?, 0)", (s,))

    conn.commit()

def salvar_questao(sistema, dificuldade, questao, acertou, tags, status="answered"):
    conn = get_conn()
    q_id = str(uuid.uuid4())
    
    conn.execute("""
        INSERT INTO questions VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        q_id, sistema, dificuldade, json.dumps(questao, ensure_ascii=False),
        questao["correct"], int(acertou), status,
        datetime.now(timezone.utc).isoformat()
    ))

    for tag in tags:
        conn.execute("""
            INSERT INTO item_tags (object_id, object_type, tag)
            VALUES (?, ?, ?)
        """, (q_id, ItemType.QUESTION.value, tag))

    conn.commit()

def get_questions():
    conn = get_conn()
    rows = conn.execute("""
        SELECT q.*, GROUP_CONCAT(t.tag, '|') as tag_list
        FROM questions q
        LEFT JOIN item_tags t ON q.id = t.object_id AND t.object_type = 'question'
        WHERE q.status = 'answered'
        GROUP BY q.id
        ORDER BY q.created_at DESC
    """).fetchall()
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

def registrar_cooldown_tags(tags):
    conn = get_conn()
    agora = datetime.now(timezone.utc).isoformat()
    for tag in tags:
        conn.execute("""
            INSERT INTO tag_cooldowns (tag, last_seen) VALUES (?, ?)
            ON CONFLICT(tag) DO UPDATE SET last_seen = excluded.last_seen
        """, (tag, agora))
    conn.commit()

def get_tags_em_cooldown(horas=48):
    conn = get_conn()
    rows = conn.execute("SELECT tag, last_seen FROM tag_cooldowns").fetchall()
    agora = datetime.now(timezone.utc)
    tags_bloqueadas = []
    
    for r in rows:
        try:
            last_seen = datetime.fromisoformat(r["last_seen"])
            if (agora - last_seen).total_seconds() < (horas * 3600):
                tags_bloqueadas.append(r["tag"])
        except ValueError:
            pass
            
    return tags_bloqueadas

def get_pending_questions():
    conn = get_conn()
    rows = conn.execute("""
        SELECT q.*, GROUP_CONCAT(t.tag, '|') as tag_list
        FROM questions q
        LEFT JOIN item_tags t ON q.id = t.object_id AND t.object_type = 'question'
        WHERE q.status = 'pending'
        GROUP BY q.id
        ORDER BY q.created_at ASC
    """).fetchall()
    return [dict(r) for r in rows]

def marcar_questao_respondida(q_id, is_correct):
    conn = get_conn()
    conn.execute("""
        UPDATE questions 
        SET status = 'answered', answered_correctly = ? 
        WHERE id = ?
    """, (int(is_correct), q_id))
    conn.commit()

# --- MUDAMOS AS FUNÇÕES DO ANKI PARA O DATABASE.PY ---
def hoje_str_db():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def salvar_flashcard_db(front, back, sistema, tags):
    card_id = str(uuid.uuid4())
    conn = get_conn()
    conn.execute("INSERT INTO flashcards (id, front, back, sistema) VALUES (?, ?, ?, ?)", (card_id, front, back, sistema))
    conn.execute("INSERT INTO srs_state (object_id, object_type, due, last_review) VALUES (?, ?, ?, ?)", (card_id, ItemType.FLASHCARD.value, hoje_str_db(), hoje_str_db()))
    for tag in tags:
        conn.execute("INSERT INTO item_tags (object_id, object_type, tag) VALUES (?, ?, ?)", (card_id, ItemType.FLASHCARD.value, tag))
    conn.commit()

def get_cards_hoje():
    conn = get_conn()
    rows = conn.execute("""
        SELECT f.id, f.front, f.back, f.sistema, 
               s.stability, s.difficulty, s.due, s.repetitions, s.lapses, s.last_review
        FROM flashcards f
        JOIN srs_state s ON f.id = s.object_id
        WHERE s.object_type = ? AND s.due <= ?
        ORDER BY s.due ASC
    """, (ItemType.FLASHCARD.value, hoje_str_db())).fetchall()
    return [dict(r) for r in rows]