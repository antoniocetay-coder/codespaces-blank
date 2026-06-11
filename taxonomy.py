import json


def carregar_taxonomia():
    try:
        with open("taxonomy.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


TAXONOMIA_COMPLETA = carregar_taxonomia()

TAGS_GLOBAIS_PERMITIDAS = set()
for sis, disciplinas in TAXONOMIA_COMPLETA.items():
    for disc, tags in disciplinas.items():
        if isinstance(tags, list):
            TAGS_GLOBAIS_PERMITIDAS.update(tags)
