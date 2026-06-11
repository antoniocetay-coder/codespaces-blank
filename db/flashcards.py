import uuid
from datetime import datetime, timezone

from db.core import get_conn, ItemType


def salvar_flashcard_db(front, back, sistema, tags):
    conn = get_conn()
    f_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO flashcards (id, front, back, sistema) VALUES (?, ?, ?, ?)",
        (f_id, front, back, sistema),
    )

    for tag in tags:
        conn.execute(
            "INSERT INTO item_tags (object_id, object_type, tag) VALUES (?, ?, ?)",
            (f_id, ItemType.FLASHCARD.value, tag),
        )
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
