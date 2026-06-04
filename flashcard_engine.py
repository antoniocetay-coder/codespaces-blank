import json
import streamlit as st
from google import genai
from config import MODEL_FLASHCARD
from ai_engine import limpar_json

def construir_prompt_chute_cego(edu_obj, correct_opt, correct_exp, block_redundancia):
    return f"""
You are an elite USMLE foundational tutor. 
The student encountered a concept they know ABSOLUTELY NOTHING about (Blind Guess).

EDUCATIONAL OBJECTIVE: {edu_obj}
CORRECT ANSWER ({correct_opt}): {correct_exp}

{block_redundancia}

TASK:
Generate 2 ATOMIC Q&A flashcards to build their base from scratch.
- Card 1: Ask for the classic clinical presentation, gold-standard diagnosis, or hallmark finding of the disease/concept.
- Card 2: Ask for the core pathophysiology or mechanism of action.

STRICT RULES:
1. NO CLOZE DELETIONS. Use direct questions.
2. SHORT ANSWERS: 1 to 5 words maximum.
3. DO NOT mention the distractors. Focus purely on the correct concept.
"""

def construir_prompt_duvida(edu_obj, correct_opt, correct_exp, wrong_opt, wrong_exp, block_redundancia):
    return f"""
You are an elite USMLE diagnostician. 
The student was torn between two concepts and guessed incorrectly.

EDUCATIONAL OBJECTIVE: {edu_obj}
CORRECT ANSWER ({correct_opt}): {correct_exp}
STUDENT'S CONFUSED ANSWER ({wrong_opt}): {wrong_exp}

{block_redundancia}

TASK:
Generate 2 ATOMIC Q&A flashcards focusing on HIGH-YIELD clinical facts.
- Card 1: Ask for the pathognomonic finding, mechanism, or gold-standard treatment of the CORRECT answer.
- Card 2: Ask for the pathognomonic finding, mechanism, or gold-standard treatment of the WRONG answer.

STRICT RULES:
1. NO CLOZE DELETIONS. Use direct questions.
2. SHORT ANSWERS: 1 to 5 words maximum.
3. DO NOT ask "What is the difference between X and Y?". Ask independent, standalone questions about each disease.
"""

def construir_prompt_vies(edu_obj, correct_opt, correct_exp, wrong_opt, wrong_exp, block_redundancia):
    return f"""
You are an elite USMLE cognitive behavioral tutor. 
The student was ABSOLUTELY CERTAIN about an answer, but they were DEAD WRONG.

EDUCATIONAL OBJECTIVE: {edu_obj}
CORRECT ANSWER ({correct_opt}): {correct_exp}
STUDENT'S TRAP ANSWER ({wrong_opt}): {wrong_exp}

{block_redundancia}

TASK:
Generate 1 or 2 ATOMIC Q&A flashcards highlighting the TRAP or the HIGH-YIELD fact they missed.
- Focus the question on the specific "exception", "caveat", or "hallmark feature" that makes the correct answer correct.

STRICT RULES:
1. NO CLOZE DELETIONS. Use direct questions.
2. SHORT ANSWERS: 1 to 5 words maximum.
3. DO NOT ask "Why is X not Y?". Ask a standalone question about the core concept.
"""

def formatar_contexto_redundancia(cards_banco, cards_rascunho):
    texto_banco = "\n".join([f"- Q: {c.get('front')} | A: {c.get('back')}" for c in cards_banco]) if cards_banco else "None"
    texto_rascunho = "\n".join([f"- Q: {c.get('front')} | A: {c.get('back')}" for c in cards_rascunho]) if cards_rascunho else "None"
    
    if not cards_banco and not cards_rascunho:
        return "" 

    return f"""
CRITICAL REDUNDANCY CHECK:
The student ALREADY HAS the following flashcards in their deck or current session drafts:
--- DECK (Saved):
{texto_banco}
--- DRAFTS (Unsaved session):
{texto_rascunho}

DO NOT GENERATE ANY FLASHCARD THAT TESTS A FACT ALREADY COVERED ABOVE. If the required knowledge is completely covered, return an empty array [].
"""

def orquestrar_flashcards(questao, letra_marcada, acertou, confianca, cards_banco, cards_rascunho, api_key):
    client = genai.Client(api_key=api_key)
    edu_obj = questao.get("educational_objective", "")
    correct_opt = questao.get("correct", "")
    explanations = questao.get("explanations", {})
    correct_exp = explanations.get(correct_opt, "No explanation provided.")
    wrong_exp = explanations.get(letra_marcada, "No explanation provided.")

    block_redundancia = formatar_contexto_redundancia(cards_banco, cards_rascunho)

    if confianca == "Chute Cego":
        prompt_base = construir_prompt_chute_cego(edu_obj, correct_opt, correct_exp, block_redundancia)
    elif confianca == "Dúvida entre 2" and not acertou:
        prompt_base = construir_prompt_duvida(edu_obj, correct_opt, correct_exp, letra_marcada, wrong_exp, block_redundancia)
    elif confianca == "Certeza Absoluta" and not acertou:
        prompt_base = construir_prompt_vies(edu_obj, correct_opt, correct_exp, letra_marcada, wrong_exp, block_redundancia)
    else:
        prompt_base = construir_prompt_duvida(edu_obj, correct_opt, correct_exp, letra_marcada, wrong_exp, block_redundancia)

    formato_json = """
FORMAT:
- 'front': A clear, unambiguous direct question.
- 'back': The short, atomic answer in **bold**, followed by a new paragraph starting with "**Context:**" explaining briefly WHY this is the answer.

Return ONLY valid JSON in this exact format:
{
    "cards": [
        {
            "front": "Question here?",
            "back": "**Short Answer**\\n\\n**Context:** Brief explanation here.",
            "tags": ["Tag1", "Tag2"]
        }
    ]
}
"""
    try:
        response = client.models.generate_content(
            model=MODEL_FLASHCARD,
            contents=prompt_base + "\n" + formato_json,
            config={"temperature": 0.2, "response_mime_type": "application/json"}
        )
        return json.loads(limpar_json(response.text)).get("cards", [])
    except Exception as e:
        st.error(f"⚠️ Erro ao gerar Flashcard de Intervenção: {str(e)}")
        return []

def gerar_mais_flashcards(questao, cards_banco, cards_rascunho, api_key):
    client = genai.Client(api_key=api_key)
    edu_obj = questao.get("educational_objective", "")
    block_redundancia = formatar_contexto_redundancia(cards_banco, cards_rascunho)

    prompt = f"""
You are an elite USMLE tutor. The student wants to explore THIS SAME TOPIC further to ensure absolute mastery.

EDUCATIONAL OBJECTIVE: {edu_obj}

{block_redundancia}

TASK:
Generate 1 or 2 NEW, ATOMIC Q&A flashcards exploring a DIFFERENT angle of the educational objective. 
If the existing cards ask about the mechanism, you MUST ask about the diagnosis, clinical presentation, or treatment.

STRICT SUPERMEMO RULES:
1. NO CLOZE DELETIONS. Direct questions only.
2. SHORT ANSWERS: 1 to 5 words max.
3. DIFFERENT ANGLE: You MUST NOT test the exact same fact already covered in the existing cards.

FORMAT:
Return ONLY valid JSON in this exact format:
{{
    "cards": [
        {{
            "front": "Question here?",
            "back": "**Short Answer**\\n\\n**Context:** Brief context.",
            "tags": ["Expanded_Review"]
        }}
    ]
}}
"""
    try:
        response = client.models.generate_content(
            model=MODEL_FLASHCARD,
            contents=prompt,
            config={"temperature": 0.4, "response_mime_type": "application/json"}
        )
        return json.loads(limpar_json(response.text)).get("cards", [])
    except Exception as e:
        st.error(f"⚠️ Erro ao expandir flashcards: {str(e)}")
        return []

def gerar_flashcard_sob_demanda(questao, pedido_usuario, cards_banco, cards_rascunho, api_key):
    client = genai.Client(api_key=api_key)
    edu_obj = questao.get("educational_objective", "")
    opcoes = "\n".join(questao.get("options", []))
    explanations = json.dumps(questao.get("explanations", {}), indent=2)

    block_redundancia = formatar_contexto_redundancia(cards_banco, cards_rascunho)

    prompt = f"""
You are an elite USMLE tutor. 

QUESTION CONTEXT:
Objective: {edu_obj}
Options: {opcoes}
Explanations: {explanations}

STUDENT'S SPECIFIC REQUEST:
"{pedido_usuario}"

{block_redundancia}

TASK:
Focus PURELY on the STUDENT'S SPECIFIC REQUEST. Generate 1 or 2 ATOMIC Q&A flashcards that answer their exact doubt.

STRICT SUPERMEMO RULES:
1. NO CLOZE DELETIONS. Use direct questions.
2. SHORT ANSWERS: 1 to 5 words max.

FORMAT:
Return ONLY valid JSON in this exact format:
{{
    "cards": [
        {{
            "front": "Question here?",
            "back": "**Short Answer**\\n\\n**Context:** Brief explanation here.",
            "tags": ["Targeted_Review"]
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
        st.error(f"⚠️ Erro ao gerar Flashcard sob demanda: {str(e)}")
        return []
    
def gerar_flashcards_do_tutor(explicacao, cards_banco, cards_rascunho, api_key):
    client = genai.Client(api_key=api_key)
    block_redundancia = formatar_contexto_redundancia(cards_banco, cards_rascunho)
    
    prompt = f"""
You are an expert USMLE Anki card creator.
A tutor just explained a concept to a student:

TUTOR'S EXPLANATION:
{explicacao}

{block_redundancia}

TASK:
Extract the most high-yield, testable facts from this explanation and create 1 or 2 ATOMIC Q&A flashcards.
CRITICAL: Do NOT generate a card that tests the same concept as the "EXISTING FLASHCARDS" listed above. You must find a NEW angle from the explanation.

STRICT SUPERMEMO RULES:
1. NO CLOZE DELETIONS. Use direct questions.
2. SHORT ANSWERS: 1 to 5 words max.
3. FOCUS ON CORE CONCEPT: Ask about the exact mechanism, definition, or clinical feature explained by the tutor.

FORMAT:
Return ONLY valid JSON in this exact format:
{{
    "cards": [
        {{
            "front": "Question here?",
            "back": "**Short Answer**\\n\\n**Context:** Brief context.",
            "tags": ["Tutor_Expansion"]
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
        st.error(f"⚠️ Erro ao gerar card do tutor: {str(e)}")
        return []