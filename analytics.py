from db.core import get_conn


def get_tag_stats():
    conn = get_conn()
    rows = conn.execute("""
        SELECT tag, correct, total, mastery_prob
        FROM tag_stats
    """).fetchall()
    return {
        r["tag"]: {
            "correct": r["correct"],
            "total": r["total"],
            "mastery_prob": r["mastery_prob"],
        }
        for r in rows
    }


def get_weak_tags(limit=5, allowed_tags=None):
    stats = get_tag_stats()
    if not stats:
        return []

    data = []
    for tag, s in stats.items():
        if allowed_tags and tag not in allowed_tags:
            continue
        if s["total"] == 0:
            continue
        prob = (
            s["mastery_prob"]
            if s["mastery_prob"] is not None
            else (s["correct"] / s["total"])
        )
        data.append((tag, prob))

    data.sort(key=lambda x: x[1])
    return [x[0] for x in data[:limit]]


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
