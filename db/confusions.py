from datetime import datetime, timezone, timedelta

from db.core import get_conn


def registrar_confusao(tag_correct, tag_confused):
    conn = get_conn()
    agora = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO confusion_pairs (tag_correct, tag_confused, count, last_seen)
           VALUES (?, ?, 1, ?)
           ON CONFLICT(tag_correct, tag_confused)
           DO UPDATE SET count = count + 1, last_seen = excluded.last_seen""",
        (tag_correct, tag_confused, agora),
    )
    conn.commit()


def get_top_confounders(tag_correct, limit=3):
    conn = get_conn()
    rows = conn.execute(
        """SELECT tag_confused
           FROM confusion_pairs
           WHERE tag_correct = ?
           ORDER BY count DESC
           LIMIT ?""",
        (tag_correct, limit),
    ).fetchall()
    return [r["tag_confused"] for r in rows]


def get_global_confusions(limit=10):
    conn = get_conn()
    rows = conn.execute(
        """SELECT tag_correct, tag_confused, count
           FROM confusion_pairs
           ORDER BY count DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_tags_em_cooldown(horas=48):
    conn = get_conn()
    corte_tempo = (
        (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
    )
    rows = conn.execute(
        """SELECT DISTINCT t.tag
           FROM item_tags t
           JOIN questions q ON t.object_id = q.id
           WHERE q.created_at >= ?""",
        (corte_tempo,),
    ).fetchall()
    return [r["tag"] for r in rows]


def registrar_cooldown_tags(tags):
    pass
