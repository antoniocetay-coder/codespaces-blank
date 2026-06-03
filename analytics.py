from database import get_conn

def get_tag_stats():
    conn = get_conn()
    # Adicionamos a coluna mastery_prob na busca
    rows = conn.execute("""
        SELECT tag, correct, total, mastery_prob
        FROM tag_stats
    """).fetchall()

    return {
        r["tag"]: {
            "correct": r["correct"],
            "total": r["total"],
            "mastery_prob": r["mastery_prob"]
        }
        for r in rows
    }

def get_weak_tags(limit=5, allowed_tags=None):
    stats = get_tag_stats()
    if not stats: return []

    data = []
    for tag, s in stats.items():
        if allowed_tags and tag not in allowed_tags:
            continue
        if s["total"] == 0:
            continue

        # Usa a probabilidade do BKT se existir, senão usa acertos/total
        prob = s["mastery_prob"] if s["mastery_prob"] is not None else (s["correct"] / s["total"])
        data.append((tag, prob))

    # Ordena pelas de menor probabilidade (mais fracas)
    data.sort(key=lambda x: x[1])
    return [x[0] for x in data[:limit]]