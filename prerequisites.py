import os
import json


def _carregar_prerequisites():
    path = os.path.join(os.path.dirname(__file__), "prerequisites.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


PREREQUISITES = _carregar_prerequisites()


def interceptar_com_prerequisitos(tags_alvo, stats):
    tags_finais = []
    for tag in tags_alvo:
        prereqs = PREREQUISITES.get(tag, [])
        foi_substituida = False

        for prereq in prereqs:
            s = stats.get(prereq, {"correct": 0, "total": 0, "mastery_prob": 0.15})
            prob = s.get("mastery_prob")
            if prob is None:
                prob = 0.15

            if prob < 0.65:
                if prereq not in tags_finais:
                    tags_finais.append(prereq)
                foi_substituida = True
                break

        if not foi_substituida and tag not in tags_finais:
            tags_finais.append(tag)

    return tags_finais
