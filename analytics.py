from database import get_conn

def get_tag_stats():

    conn = get_conn()

    rows = conn.execute("""
        SELECT tag, correct, total
        FROM tag_stats
    """).fetchall()

    return {
        r["tag"]: {
            "correct": r["correct"],
            "total": r["total"]
        }
        for r in rows
    }

def get_weak_tags(limit=5):

    stats = get_tag_stats()

    if not stats:
        return []

    data = []

    for tag, s in stats.items():

        if s["total"] == 0:
            continue

        pct = s["correct"] / s["total"]

        data.append((tag, pct))

    data.sort(key=lambda x: x[1])

    return [x[0] for x in data[:limit]]