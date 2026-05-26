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
    if inicio != -1 and fim != -1:
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
    "content_tags"
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

    if allowed_tags:
        invalid_tags = [t for t in tags_geradas if t not in allowed_tags]
        if invalid_tags:
            return False, f"A IA alucinou! Tags inventadas que não estão no First Aid: {invalid_tags}"

    return True, "OK"

# ==============================================================================
# AI ENGINE
# ==============================================================================
def gerar_prompt(sistema, dificuldade, tags_alvo):
    alvos_texto = ", ".join(tags_alvo) if tags_alvo else "General topics"
    
    tax_sistema = TAXONOMIA_COMPLETA.get(sistema, {})
    tax_json = json.dumps(tax_sistema, indent=2)

    return f"""
You are an elite NBME-style USMLE question writer.
Generate ONE high-quality USMLE clinical vignette.

SYSTEM: {sistema}
DIFFICULTY: {dificuldade}

TARGET TAGS (MANDATORY): {alvos_texto}
You MUST construct the vignette to test the concepts listed in the TARGET TAGS above.

STRICT TAXONOMY RULE:
You MUST classify the question using AT LEAST 6 and UP TO 10 exact tags from the JSON below. 
You MUST mix disciplines (e.g., include Pathology, Pharmacology, AND Physiology tags).
Do NOT invent tags. Do NOT use tags outside this list.

ALLOWED TAXONOMY FOR {sistema}:
{tax_json}

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
        "Pathology Tag from list",
        "Pharmacology Tag from list",
        "Physiology Tag from list",
        "Anatomy Tag from list",
        "Additional Tag 5 from list",
        "Additional Tag 6 from list",
        "Additional Tag 7 from list"
    ]
}}
"""

def gerar_questao(sistema, dificuldade, api_key, tags_alvo=None):
    # Se o Scheduler não enviou tags_alvo, ele puxa das fraquezas tradicionais
    if not tags_alvo:
        from analytics import get_weak_tags
        tax_sistema = TAXONOMIA_COMPLETA.get(sistema, {})
        allowed_tags = set()
        for d, t_list in tax_sistema.items():
            if isinstance(t_list, list):
                allowed_tags.update(t_list)
        tags_alvo = get_weak_tags(limit=5, allowed_tags=allowed_tags)

    client = genai.Client(api_key=api_key)
    prompt = gerar_prompt(sistema, dificuldade, tags_alvo)

    try:
        response = client.models.generate_content(
            model=MODEL_QBANK,
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
            print(f"Erro de Validação: {msg}")
            return None

        questao["correct"] = questao["correct"].strip().upper()[0]
        return questao

    except Exception as e:
        print(f"Erro na API: {e}")
        return None

# ==============================================================================
# SMART FLASHCARDS
# ==============================================================================
def gerar_flashcards_ia(questao, letra_marcada, cards_existentes, api_key):
    client = genai.Client(api_key=api_key)
    
    edu_obj = questao.get("educational_objective", "")
    correct_opt = questao["correct"]
    correct_exp = questao.get("explanations", {}).get(correct_opt, "")
    wrong_exp = questao.get("explanations", {}).get(letra_marcada, "")
    
    if cards_existentes:
        cards_texto = "\n".join([f"- Front: {c['front']}\n  Back: {c['back']}" for c in cards_existentes])
    else:
        cards_texto = "The student has NO existing flashcards for these topics."

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
2. Assess if the student lacks foundational knowledge: if the wrong answer suggests they don't even know the basics of the core disease/concept, you must create a Foundational Card first.
3. CRITICAL REDUNDANCY CHECK: Look at the EXISTING FLASHCARDS. If a concept is ALREADY covered, DO NOT create a duplicate. 
4. Create 1 to 3 ATOMIC "Fill-in-the-blank" (Cloze style) flashcards:
   - Card 1 (Foundational - Optional): Tests the most basic definition, presentation, or cause of the core disease/drug.
   - Card 2 (Specific): Tests the exact detail/mechanism the student missed in the question.

FORMAT RULES:
- 'front': sentence with the key concept replaced by "[...]".
- 'back': MUST contain the complete sentence with the missing word(s) in **bold**, followed by a new paragraph starting with "**Context:**" explaining the disease/phenomenon in 1-2 concise sentences.
- If existing cards are enough, return an empty array.

Example:
Front: "In senile aortic stenosis, the valve leaflets undergo [...] calcification."
Back: "In senile aortic stenosis, the valve leaflets undergo **dystrophic** calcification.\n\n**Context:** Dystrophic calcification occurs in damaged or necrotic tissues in the setting of normal serum calcium and phosphate levels."
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
            model=MODEL_FLASHCARD,
            contents=prompt,
            config={"temperature": 0.2, "response_mime_type": "application/json"}
        )
        return json.loads(limpar_json(response.text)).get("cards", [])
    except Exception as e:
        return []