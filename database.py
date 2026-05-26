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
        conn.execute("INSERT OR IGNORE INTO erros_por_sistema (sistema, total) VALUES (?, 0)", (s,))

    conn.commit()

# --- ATUALIZADO: Agora recebe as tags e salva nas duas tabelas ---
def salvar_questao(sistema, dificuldade, questao, acertou, tags):
    conn = get_conn()
    q_id = str(uuid.uuid4())
    
    # 1. Salva a questão
    conn.execute("""
        INSERT INTO questions VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        q_id, sistema, dificuldade, json.dumps(questao, ensure_ascii=False),
        questao["correct"], int(acertou),
        datetime.now(timezone.utc).isoformat()
    ))

    # 2. Salva as tags
    for tag in tags:
        conn.execute("""
            INSERT INTO item_tags (object_id, object_type, tag)
            VALUES (?, ?, ?)
        """, (q_id, ItemType.QUESTION.value, tag))

    conn.commit()

# --- ATUALIZADO: Traz as questões já costuradas com as tags ---
def get_questions():
    conn = get_conn()
    rows = conn.execute("""
        SELECT q.*, GROUP_CONCAT(t.tag, '|') as tag_list
        FROM questions q
        LEFT JOIN item_tags t ON q.id = t.object_id AND t.object_type = 'question'
        GROUP BY q.id
        ORDER BY q.created_at DESC
    """).fetchall()
    return [dict(r) for r in rows]
def get_flashcards_by_tags(tags):
    if not tags:
        return []
    
    conn = get_conn()
    
    # Cria os "?" para o comando SQL dependendo de quantas tags existem
    placeholders = ",".join(["?"] * len(tags))
    
    query = f"""
        SELECT DISTINCT f.front, f.back
        FROM flashcards f
        JOIN item_tags t ON f.id = t.object_id AND t.object_type = 'flashcard'
        WHERE t.tag IN ({placeholders})
    """
    
    rows = conn.execute(query, tags).fetchall()
    return [{"front": r["front"], "back": r["back"]} for r in rows]