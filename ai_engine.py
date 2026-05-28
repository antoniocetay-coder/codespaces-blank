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
    "content_tags",
    "distractor_tags"
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
            return False, f"A IA alucinou nas tags da questão: {invalid_tags}"

        dist_tags = q.get("distractor_tags", {})
        for letra, tag in dist_tags.items():
            if tag not in allowed_tags:
                return False, f"A IA alucinou na tag do distrator {letra}: '{tag}'"

    return True, "OK"

# ==============================================================================
# AI ENGINE
# ==============================================================================
def gerar_prompt(sistema, difficulty, weak_tags, tags_alvo=None):
    weak_text = ", ".join(weak_tags) if weak_tags else "None"
    
    focus_instruction = f"FOCUS WEAK AREAS: {weak_text}"
    confounder_instruction = ""
    
    if tags_alvo:
        focus_instruction += f"\nCRITICAL: The question MUST strictly test one of these tags: {', '.join(tags_alvo)}"
        
        # BUSCA OS CONFUNDIDORES NO BANCO
        from database import get_top_confounders
        confounders = []
        for tag in tags_alvo:
            confounders.extend(get_top_confounders(tag))
        
        if confounders:
            confounders = list(set(confounders))
            confounder_instruction = f"""
STUDENT'S KNOWN CONFUSIONS:
The student frequently confuses the correct answer with these concepts: {', '.join(confounders)}
YOU MUST include at least one of these concepts as a highly plausible DISTRACTOR (incorrect option) and explain why it is wrong in the explanations.
"""
            
    tax_sistema = TAXONOMIA_COMPLETA.get(sistema, {})
    tax_json = json.dumps(tax_sistema, indent=2)

    return f"""
You are an elite NBME-style USMLE question writer.
Generate ONE high-quality USMLE clinical vignette.

SYSTEM: {sistema}
DIFFICULTY: {difficulty}
{focus_instruction}
{confounder_instruction}

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
        "Tag 2 from list"
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

def gerar_questao(sistema, difficulty, api_key, tags_alvo=None):
    from analytics import get_weak_tags
    tax_sistema = TAXONOMIA_COMPLETA.get(sistema, {})
    allowed_tags = set()
    for d, t_list in tax_sistema.items():
        if isinstance(t_list, list):
            allowed_tags.update(t_list)
    weak_tags = get_weak_tags(limit=5, allowed_tags=allowed_tags)

    client = genai.Client(api_key=api_key)
    prompt = gerar_prompt(sistema, difficulty, weak_tags, tags_alvo=tags_alvo)

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
            print(f"Validation error: {msg}")
            return None
        questao["correct"] = questao["correct"].strip().upper()[0]
        return questao
    except Exception as e:
        print(f"Erro ao gerar questão: {str(e)}")
        return None

def gerar_flashcards_ia(questao, letra_marcada, api_key):
    client = genai.Client(api_key=api_key)
    edu_obj = questao.get("educational_objective", "")
    correct_opt = questao.get("correct", "")
    
    explanations = questao.get("explanations", {})
    correct_exp = explanations.get(correct_opt, "No explanation provided.")
    wrong_exp = explanations.get(letra_marcada, "No explanation provided.")

    prompt = f"""
You are an elite USMLE tutor and a strict follower of Piotr Wozniak's "20 Rules of Formulating Knowledge".
The student answered a USMLE question incorrectly.

EDUCATIONAL OBJECTIVE: {edu_obj}
CORRECT ANSWER ({correct_opt}): {correct_exp}
STUDENT'S WRONG ANSWER ({letra_marcada}): {wrong_exp}

TASK:
Analyze the student's knowledge gap based on their WRONG ANSWER. Generate 1 to 3 ATOMIC, highly-effective Q&A (Question & Answer) flashcards to fix this exact gap.

STRICT SUPERMEMO RULES:
1. MINIMUM INFORMATION PRINCIPLE: Test exactly ONE specific concept per card. 
2. NO CLOZE DELETIONS: Use direct questions. Do NOT use fill-in-the-blank or "[...]".
3. NO LISTS: Never ask "What are the symptoms?". Instead, ask a mechanistic or distinguishing question.
4. FOCUS ON MECHANISM & CLINICAL REASONING: Ask WHY something happens (Pathophysiology, Mechanism of Action) or how to clinically distinguish it.
5. SHORT ANSWERS: The answer must be 1 to 5 words max. 

FORMAT:
- 'front': A clear, unambiguous direct question.
- 'back': The short, atomic answer in **bold**, followed by a new paragraph starting with "**Context:**" explaining briefly WHY this is the answer.

Return ONLY valid JSON in this exact format:
{{
    "cards": [
        {{
            "front": "Question here?",
            "back": "**Short Answer**\n\n**Context:** Brief explanation here.",
            "tags": ["Tag1", "Tag2"]
        }}
    ]
}}
"""
    try:
        response = client.models.generate_content(
            model=MODEL_FLASHCARD,
            contents=prompt,
            config={
                "temperature": 0.2,
                "response_mime_type": "application/json"
            }
        )
        
        texto_limpo = limpar_json(response.text)
        dados = json.loads(texto_limpo)
        return dados.get("cards", [])
        
    except Exception as e:
        st.error(f"⚠️ Erro na comunicação com o Gemini para Flashcards: {str(e)}")
        return []