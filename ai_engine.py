import json
import streamlit as st
from google import genai
from config import *

# ==============================================================================
# CARREGAMENTO DA TAXONOMIA
# ==============================================================================
def carregar_taxonomia():
    try:
        with open("taxonomy.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

TAXONOMIA_COMPLETA = carregar_taxonomia()

def limpar_json(texto):
    texto = texto.strip().lstrip("\ufeff")
    if "```" in texto:
        linhas = texto.splitlines()
        linhas = [l for l in linhas if not l.strip().startswith("```")]
        texto = "\n".join(linhas)

    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio != -1 and f != -1:
        texto = texto[inicio:fim+1]
    return texto

# ==============================================================================
# VALIDAÇÃO
# ==============================================================================
SCHEMA_OBRIGATORIO = {
    "vignette",
    "options",
    "correct",
    "explanations",
    "educational_objective",
    "content_tags",
    "distractor_tags"  # <-- ADICIONADO AO SCHEMA OBRIGATÓRIO
}

def validar_questao(q, sistema):
    if not isinstance(q, dict):
        return False, "A IA não devolveu um formato de dicionário válido."

    faltando = SCHEMA_OBRIGATORIO - q.keys()
    if faltando:
        return False, f"Faltam informações no JSON gerado: {faltando}"

    tax_sistema = TAXONOMIA_COMPLETA.get(sistema, {})
    allowed_tags = set()
    for disciplina, tags in tax_sistema.items():
        if isinstance(tags, list):
            allowed_tags.update(tags)

    tags_geradas = q.get("content_tags", [])
    if not tags_geradas:
        return False, "A IA não gerou nenhuma Tag para a questão."

    # Valida as tags principais da questão contra a taxonomia
    if allowed_tags:
        invalid_tags = [t for t in tags_geradas if t not in allowed_tags]
        if invalid_tags:
            return False, f"A IA alucinou nas tags da questão: {invalid_tags}"

        # --- NOVA VALIDAÇÃO: Bloqueia se a IA alucinar nas tags dos distratores! ---
        dist_tags = q.get("distractor_tags", {})
        for letra, tag in dist_tags.items():
            if tag not in allowed_tags:
                return False, f"A IA alucinou na tag do distrator {letra}: '{tag}'"

    return True, "OK"

# ==============================================================================
# AI ENGINE
# ==============================================================================
def gerar_prompt(sistema, difficulty, weak_tags):
    weak_text = ", ".join(weak_tags) if weak_tags else "None"
    tax_sistema = TAXONOMIA_COMPLETA.get(sistema, {})
    tax_json = json.dumps(tax_sistema, indent=2)

    return f"""
You are an elite NBME-style USMLE question writer.
Generate ONE high-quality USMLE clinical vignette.

SYSTEM: {sistema}
DIFFICULTY: {difficulty}
FOCUS WEAK AREAS: {weak_text}

STRICT TAXONOMY RULE:
You MUST classify the question using 4 to 10 exact tags from the JSON below.
Do NOT invent tags. Do NOT use tags outside this list.

ALLOWED TAXONOMY FOR {sistema}:
{tax_json}

STRICT DISTRACTOR TAGGING RULE:
For every single option in "options" (A, B, C, D, E), you MUST associate it with its specific medical concept/tag from the ALLOWED TAXONOMY above.
- The correct option must point to the correct concept tested.
- Each distractor (incorrect option) must point to the specific decoy/distractor concept it represents.
- Output this mapping in the "distractor_tags" object. All tags in "distractor_tags" must be exact matches from the ALLOWED TAXONOMY.

STRICT REQUIREMENTS:
- NBME style (realistic clinical reasoning, mechanism-based)
- Plausible distractors with explanations
- No giveaway buzzwords
- Single best answer
- Return ONLY valid JSON.

{{
    "vignette": "A 45-year-old man presents with...",
    "options": [
        "A) ...",
        "B) ...",
        "C) ...",
        "D) ...",
        "E) ..."
    ],
    "correct": "A",
    "explanations": {{
        "A": "...",
        "B": "...",
        "C": "...",
        "D": "...",
        "E": "..."
    }},
    "educational_objective": "...",
    "content_tags": [
        "Tag 1 from list",
        "Tag 2 from list",
        "Tag 3 from list",
        "Tag 4 from list",
        "... add up to 10 tags if relevant"
    ],
    "distractor_tags": {{
        "A": "Exact Tag from list for Option A",
        "B": "Exact Tag from list for Option B",
        "C": "Exact Tag from list for Option C",
        "D": "Exact Tag from list for Option D",
        "E": "Exact Tag from list for Option E"
    }}
}}
"""

def gerar_questao(sistema, difficulty, api_key):
    from analytics import get_weak_tags
    tax_sistema = TAXONOMIA_COMPLETA.get(sistema, {})
    allowed_tags = set()
    for d, t_list in tax_sistema.items():
        if isinstance(t_list, list):
            allowed_tags.update(t_list)
    weak_tags = get_weak_tags(limit=5, allowed_tags=allowed_tags)

    client = genai.Client(api_key=api_key)
    prompt = gerar_prompt(sistema, difficulty, weak_tags)

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={
                "temperature": 0.4,
                "response_mime_type": "application/json"
            }
        )
        texto = limpar_json(response.text)
        questao = json.loads(texto)
        is_valid, msg = validar_questao(questao, sistema)
        if not is_valid:
            st.error(f"Validation error: {msg}")
            return None
        questao["correct"] = questao["correct"].strip().upper()[0]
        return questao
    except Exception as e:
        st.error(str(e))
        return None

def gerar_flashcards_ia(questao, letra_marcada, cards_existentes, api_key):
    client = genai.Client(api_key=api_key)
    edu_obj = questao.get("educational_objective", "")
    correct_opt = questao["correct"]
    correct_exp = questao.get("explanations", {}).get(correct_opt, "")
    wrong_exp = questao.get("explanations", {}).get(letra_marcada, "")
    if cards_existentes:
        cards_texto = "\n".join([f"- Front: {c['front']}\n  Back: {c['back']}" for c in cards_existentes])
    else:
        cards_texto = "No existing cards."

    prompt = f"""
You are an expert USMLE tutor and Anki card creator.
The student answered a USMLE question incorrectly.

EDUCATIONAL OBJECTIVE: {edu_obj}
CORRECT ANSWER ({correct_opt}): {correct_exp}
STUDENT'S WRONG ANSWER ({letra_marcada}): {wrong_exp}

EXISTING FLASHCARDS IN DECK:
{cards_texto}

TASK:
1. Identify the exact knowledge gap based on the WRONG ANSWER.
2. Assess if the student lacks foundational knowledge.
3. CRITICAL REDUNDANCY CHECK: If a concept is ALREADY covered in the EXISTING FLASHCARDS, DO NOT create a duplicate.
4. Create 1 to 3 ATOMIC "Fill-in-the-blank" (Cloze style) flashcards:
   - Card 1 (Foundational - Optional): Basic definition or presentation of the disease/concept.
   - Card 2 (Specific): Tests exact missed fact from objective.

FORMAT RULES:
- 'front': sentence with the key concept replaced by "[...]".
- 'back': MUST contain the complete sentence with the missing word(s) in **bold**, followed by a new paragraph starting with "**Context:**" explaining the disease/phenomenon in 1-2 concise sentences.
- If existing cards are enough, return an empty array.

Example:
Front: "In senile aortic stenosis, the valve leaflets undergo [...] calcification."
Back: "In senile aortic stenosis, the valve leaflets undergo **dystrophic** calcification.\n\n**Context:** Dystrophic calcification occurs in damaged or necrotic tissues."

Return ONLY valid JSON:
{{
    "cards": [
        {{
            "front": "...",
            "back": "...",
            "tags": ["Tag1", "Tag2"]
        }}
    ]
}}
"""
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={
                "temperature": 0.2,
                "response_mime_type": "application/json"
            }
        )
        return json.loads(limpar_json(response.text)).get("cards", [])
    except Exception as e:
        return []