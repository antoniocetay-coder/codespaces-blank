import json
import uuid
from datetime import datetime, timezone

from db.core import get_conn, ItemType


def salvar_questao(sistema, dificuldade, questao, acertou, tags, status="answered"):
    conn = get_conn()
    q_id = str(uuid.uuid4())
    ans_val = None if status == "pending" else int(acertou)

    conn.execute(
        """INSERT INTO questions
           (id, sistema, dificuldade, question_json, correct_answer,
            answered_correctly, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            q_id,
            sistema,
            dificuldade,
            json.dumps(questao, ensure_ascii=False),
            questao["correct"],
            ans_val,
            datetime.now(timezone.utc).isoformat(),
        ),
    )

    for tag in tags:
        conn.execute(
            "INSERT INTO item_tags (object_id, object_type, tag) VALUES (?, ?, ?)",
            (q_id, ItemType.QUESTION.value, tag),
        )
    conn.commit()


def marcar_questao_respondida(q_id, acertou, time_taken=None, confidence=None):
    conn = get_conn()
    conn.execute(
        """UPDATE questions
           SET answered_correctly = ?, time_taken_seconds = ?, confidence_level = ?
           WHERE id = ?""",
        (int(acertou), time_taken, confidence, q_id),
    )
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
