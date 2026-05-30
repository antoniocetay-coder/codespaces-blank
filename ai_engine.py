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
# AI ENGINE - BATCH GENERATOR
# ==============================================================================
def gerar_prompt_lote(sistema, difficulty, tags_alvo, num_questoes):
    """Novo prompt focado em gerar múltiplas questões de uma só vez."""
    tags_text = ", ".join(tags_alvo) if tags_alvo else "None"
    
    tax_sistema = TAXONOMIA_COMPLETA.get(sistema, {})
    tax_json = json.dumps(tax_sistema, indent=2)

    # Injeta a instrução de distratores baseada no histórico de confusões
    confounder_instruction = ""
    if tags_alvo:
        from database import get_top_confounders
        confounders = []
        for tag in tags_alvo:
            confounders.extend(get_top_confounders(tag))
        
        if confounders:
            confounders = list(set(confounders))
            confounder_instruction = f"""
STUDENT'S KNOWN CONFUSIONS:
The student frequently confuses the correct answer with these concepts: {', '.join(confounders)}
If applicable to the vignette, YOU MUST include at least one of these concepts as a highly plausible DISTRACTOR (incorrect option).
"""

    return f"""
You are an elite NBME-style USMLE question writer.
Generate EXACTLY {num_questoes} high-quality USMLE clinical vignettes.

SYSTEM: {sistema}
DIFFICULTY: {difficulty}
TARGET CONCEPTS: {tags_text}
CRITICAL: You MUST write exactly ONE question for each of the TARGET CONCEPTS listed above to ensure no repetition within this batch.

{confounder_instruction}

STRICT TAXONOMY RULE:
You MUST classify each question using exact tags from the JSON below.
Do NOT invent tags. Do NOT use tags outside this list.

ALLOWED TAXONOMY FOR {sistema}:
{tax_json}

STRICT DISTRACTOR TAGGING RULE:
For every single option in "options" (A, B, C, D, E), you MUST associate it with its specific medical concept/tag from the ALLOWED TAXONOMY above.
- The correct option must point to the correct concept tested.
- Each distractor (incorrect option) must point to the specific decoy/distractor concept it represents.

RETURN FORMAT:
You MUST return a valid JSON object containing an array called "questions". Do not use markdown blocks outside the JSON.

{{
  "questions": [
    {{
        "vignette": "A 45-year-old man presents with...",
        "options": ["A) ...", "B) ...", "C) ...", "D) ...", "E) ..."],
        "correct": "A",
        "explanations": {{
            "A": "...", "B": "...", "C": "...", "D": "...", "E": "..."
        }},
        "educational_objective": "...",
        "content_tags": ["Tag 1", "Tag 2"],
        "distractor_tags": {{
            "A": "Exact Tag for Option A",
            "B": "Exact Tag for Option B",
            "C": "Exact Tag for Option C",
            "D": "Exact Tag for Option D",
            "E": "Exact Tag for Option E"
        }}
    }}
  ]
}}
"""

def gerar_lote_questoes(sistema, difficulty, api_key, tags_alvo, num_questoes):
    """Chama a API uma única vez e retorna uma lista de questões validadas."""
    client = genai.Client(api_key=api_key)
    prompt = gerar_prompt_lote(sistema, difficulty, tags_alvo, num_questoes)

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
        dados = json.loads(texto)
        
        questoes_geradas = dados.get("questions", [])
        questoes_validas = []
        
        for q in questoes_geradas:
            is_valid, msg = validar_questao(q, sistema)
            if is_valid:
                q["correct"] = q["correct"].strip().upper()[0]
                questoes_validas.append(q)
            else:
                print(f"Questão descartada por falha de validação: {msg}")
                
        return questoes_validas
        
    except Exception as e:
        print(f"Erro ao gerar lote de questões: {str(e)}")
        return []

# Usado na Tab 2 (Prática Focada) que gera apenas 1 questão por vez
def gerar_questao(sistema, difficulty, api_key, tags_alvo=None):
    res = gerar_lote_questoes(sistema, difficulty, api_key, tags_alvo, 1)
    return res[0] if res else None

def explicar_duvida_tutor(contexto_material, duvida_aluno, api_key):
    """
    Tutor de IA em formato de Chat. 
    Lê o flashcard/questão e responde diretamente a dúvida do aluno em texto claro.
    """
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
You are an elite, empathetic USMLE tutor (Step 1 and Step 2 CK).
The student is currently studying the following material (Flashcard or Question):

MATERIAL CONTEXT:
{contexto_material}

STUDENT'S DOUBT:
"{duvida_aluno}"

TASK:
Provide a highly accurate, concise, and easy-to-understand explanation.
- Speak directly to the student.
- Focus STRICTLY on clarifying their doubt using the provided context.
- Use bold text for key physiological or pharmacological mechanisms.
- Keep your answer between 1 and 3 short paragraphs. DO NOT write a giant essay.
"""
    try:
        response = client.models.generate_content(
            model=MODEL_FLASHCARD, # Usamos o modelo rápido para resposta estilo chat
            contents=prompt,
            config={
                "temperature": 0.4, # Um pouco de criatividade para ele ser mais didático
                # Sem response_mime_type, pois queremos texto normal, não JSON
            }
        )
        return response.text
    except Exception as e:
        return f"⚠️ Erro ao contatar o Tutor: {str(e)}"