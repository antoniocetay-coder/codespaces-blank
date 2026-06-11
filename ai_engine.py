import json
import requests
import streamlit as st
from ai_client import chat_json, chat_text
from config import MODEL_QBANK, MODEL_FLASHCARD
from taxonomy import TAXONOMIA_COMPLETA
from validation import limpar_json, validar_questao

# ==============================================================================
# AI ENGINE - BATCH GENERATOR (Otimizado)
# ==============================================================================
def gerar_prompt_lote(sistema, difficulty, cognitive_order, tags_alvo, num_questoes):
    tags_text = ", ".join(tags_alvo) if tags_alvo else "None"
    
    # DIETA DA API: Mandamos apenas a taxonomia Relevante (Sistema Principal + General Principles)
    tax_reduzida = {}
    if sistema in TAXONOMIA_COMPLETA:
        tax_reduzida[sistema] = TAXONOMIA_COMPLETA[sistema]
    if "General_Principles" in TAXONOMIA_COMPLETA and sistema != "General_Principles":
        tax_reduzida["General_Principles"] = TAXONOMIA_COMPLETA["General_Principles"]
        
    tax_json = json.dumps(tax_reduzida, indent=2)

    confounder_instruction = ""
    if tags_alvo:
        from db.confusions import get_top_confounders
        confounders = []
        for tag in tags_alvo:
            confounders.extend(get_top_confounders(tag))
        
        if confounders:
            confounders = list(set(confounders))
            confounder_instruction = f"""
STUDENT'S KNOWN CONFUSIONS:
The student frequently confuses the correct answer with these concepts: {', '.join(confounders)}
If applicable, YOU MUST include at least one of these concepts as a highly plausible DISTRACTOR.
"""

    return f"""
You are an elite NBME-style USMLE question writer.
Generate EXACTLY {num_questoes} high-quality USMLE clinical vignettes.

PRIMARY SYSTEM: {sistema}
DIFFICULTY: {difficulty}
TARGET CONCEPTS: {tags_text}
COGNITIVE DEPTH REQUIRED: {cognitive_order}

CRITICAL RULES:
1. You MUST write exactly ONE question for each of the TARGET CONCEPTS listed above to ensure no repetition within this batch.
2. You MUST strictly adhere to the COGNITIVE DEPTH REQUIRED:
   - If "1st Order": Ask "What is the most likely diagnosis?".
   - If "2nd Order": Give away the diagnosis subtly in the vignette. Ask about the underlying mechanism, pathophysiology, or best next step.
   - If "3rd Order": Give away the diagnosis. Ask about the mechanism of action of the drug used to treat the main complication, or the embryological origin of the affected tissue.

{confounder_instruction}

STRICT TAXONOMY RULE:
You MUST classify each question using exact tags from the JSON below. Do NOT invent tags.

ALLOWED TAXONOMY:
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

def gerar_lote_questoes(sistema, difficulty, cognitive_order, api_key, tags_alvo, num_questoes):
    prompt = gerar_prompt_lote(sistema, difficulty, cognitive_order, tags_alvo, num_questoes)

    try:
        texto_bruto = chat_json(prompt, MODEL_QBANK, api_key, temperature=0.4, reasoning=True)
        texto = limpar_json(texto_bruto)

        if not texto:
            print("Erro: A IA devolveu um texto vazio.")
            return []

        dados = json.loads(texto)
        questoes_geradas = dados.get("questions", [])
        questoes_validas = []

        for q in questoes_geradas:
            is_valid, msg = validar_questao(q, sistema)
            if is_valid:
                q["correct"] = q["correct"].strip().upper()[0]
                questoes_validas.append(q)
            else:
                st.toast(f"🗑️ Questão descartada: {msg}")
                print(f"Descartada: {msg}")

        return questoes_validas

    except json.JSONDecodeError as e:
        print(f"Erro de Parse JSON: {str(e)}\nTexto retornado:\n{texto}")
        st.toast("⚠️ A IA se confundiu no formato JSON. Tentando novamente...")
        return []
    except requests.HTTPError as e:
        print(f"Erro HTTP OpenRouter: {e.response.status_code} {e.response.text}")
        st.toast(f"⚠️ Erro OpenRouter ({e.response.status_code}).")
        return []
    except Exception as e:
        print(f"Erro na API: {str(e)}")
        st.toast(f"⚠️ Erro no servidor: {str(e)}")
        return []

def gerar_questao(sistema, difficulty, api_key, tags_alvo=None):
    res = gerar_lote_questoes(sistema, difficulty, "2nd Order (Pathophysiology/Next Step in Management)", api_key, tags_alvo, 1)
    return res[0] if res else None

def explicar_duvida_tutor(contexto_material, duvida_aluno, api_key):
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
        return chat_text(prompt, MODEL_FLASHCARD, api_key, temperature=0.4, reasoning=False)
    except Exception as e:
        return f"⚠️ Erro ao contatar o Tutor: {str(e)}"