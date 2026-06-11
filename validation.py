from taxonomy import TAGS_GLOBAIS_PERMITIDAS


def limpar_json(texto):
    texto = texto.strip().lstrip("\ufeff")
    if "```" in texto:
        linhas = texto.splitlines()
        linhas = [l for l in linhas if not l.strip().startswith("```")]
        texto = "\n".join(linhas)

    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio != -1 and fim != -1:
        texto = texto[inicio : fim + 1]
    return texto


SCHEMA_OBRIGATORIO = {
    "vignette",
    "options",
    "correct",
    "explanations",
    "educational_objective",
    "content_tags",
    "distractor_tags",
}


def validar_questao(q, sistema):
    if not isinstance(q, dict):
        return False, "A IA não devolveu um formato de dicionário válido."

    faltando = SCHEMA_OBRIGATORIO - q.keys()
    if faltando:
        return False, f"Faltam informações no JSON gerado: {faltando}"

    tags_geradas = q.get("content_tags", [])
    if not tags_geradas:
        return False, "A IA não gerou nenhuma Tag para a questão."

    if TAGS_GLOBAIS_PERMITIDAS:
        invalid_tags = [t for t in tags_geradas if t not in TAGS_GLOBAIS_PERMITIDAS]
        if invalid_tags:
            return False, f"Alucinação nas content_tags: {invalid_tags}"

        dist_tags = q.get("distractor_tags", {})
        for letra, tag in dist_tags.items():
            if tag not in TAGS_GLOBAIS_PERMITIDAS:
                return False, f"Alucinação no distrator {letra}: '{tag}'"

    return True, "OK"
