import json
import streamlit as st
from google import genai
from config import MODEL_FLASHCARD
from ai_engine import limpar_json

def construir_prompt_chute_cego(edu_obj, correct_opt, correct_exp):
    return f"""
You are an elite USMLE foundational tutor. 
The student encountered a concept they know ABSOLUTELY NOTHING about (Blind Guess).

EDUCATIONAL OBJECTIVE: {edu_obj}
CORRECT ANSWER ({correct_opt}): {correct_exp}

TASK:
Ignore any distractors. The student lacks the basic foundation. 
Generate 2 ATOMIC Q&A flashcards to build their base from scratch.
- Card 1: Ask for the basic definition, classic presentation, or gold-standard diagnosis.
- Card 2: Ask for the core pathophysiology or mechanism of action.

STRICT RULES:
1. NO CLOZE DELETIONS. Use direct questions (e.g., "What is the primary mechanism of...?").
2. SHORT ANSWERS: 1 to 5 words maximum.
3. NO LISTS. 
"""

def construir_prompt_duvida(edu_obj, correct_opt, correct_exp, wrong_opt, wrong_exp):
    return f"""
You are an elite USMLE diagnostician. 
The student was torn between two similar concepts and guessed incorrectly.

EDUCATIONAL OBJECTIVE: {edu_obj}
CORRECT ANSWER ({correct_opt}): {correct_exp}
STUDENT'S CONFUSED ANSWER ({wrong_opt}): {wrong_exp}

TASK:
The student understands the basics but lacks the ability to differentiate these two concepts.
Generate 2 ATOMIC Q&A flashcards focusing strictly on CONTRAST and DIFFERENTIAL DIAGNOSIS.
- Card 1: Ask for the specific clinical or lab feature that is EXCLUSIVE to the Correct Answer.
- Card 2: Ask for the specific clinical or lab feature that is EXCLUSIVE to the Wrong Answer (to clear up the distractor).

STRICT RULES:
1. NO CLOZE DELETIONS. Use direct questions.
2. SHORT ANSWERS: 1 to 5 words maximum.
3. NO LISTS. Focus on distinguishing features.
"""

def construir_prompt_vies(edu_obj, correct_opt, correct_exp, wrong_opt, wrong_exp):
    return f"""
You are an elite USMLE cognitive behavioral tutor. 
The student was ABSOLUTELY CERTAIN about an answer, but they were DEAD WRONG. They fell for a classic trap.

EDUCATIONAL OBJECTIVE: {edu_obj}
CORRECT ANSWER ({correct_opt}): {correct_exp}
STUDENT'S TRAP ANSWER ({wrong_opt}): {wrong_exp}

TASK:
Shatter the student's cognitive bias. They fell for a "Red Herring" or an exception to the rule.
Generate 1 or 2 ATOMIC Q&A flashcards highlighting the TRAP.
- Focus the question on the specific "exception", "caveat", or "trick" that makes their assumed answer wrong in this specific context.

STRICT RULES:
1. NO CLOZE DELETIONS. Use direct questions.
2. SHORT ANSWERS: 1 to 5 words maximum.
3. Highlight the nuance.
"""

def orquestrar_flashcards(questao, letra_marcada, acertou, confianca, api_key):
    """
    Roteador cognitivo. Decide qual prompt usar baseado na metacognição do aluno.
    """
    client = genai.Client(api_key=api_key)
    
    edu_obj = questao.get("educational_objective", "")
    correct_opt = questao.get("correct", "")
    explanations = questao.get("explanations", {})
    
    correct_exp = explanations.get(correct_opt, "No explanation provided.")
    wrong_exp = explanations.get(letra_marcada, "No explanation provided.")

    # ==========================================
    # ROTEAMENTO METACOGNITIVO
    # ==========================================
    if confianca == "Chute Cego":
        prompt_base = construir_prompt_chute_cego(edu_obj, correct_opt, correct_exp)
    
    elif confianca == "Dúvida entre 2" and not acertou:
        prompt_base = construir_prompt_duvida(edu_obj, correct_opt, correct_exp, letra_marcada, wrong_exp)
        
    elif confianca == "Certeza Absoluta" and not acertou:
        prompt_base = construir_prompt_vies(edu_obj, correct_opt, correct_exp, letra_marcada, wrong_exp)
        
    else:
        prompt_base = construir_prompt_duvida(edu_obj, correct_opt, correct_exp, letra_marcada, wrong_exp)

    # Injeção das regras de formatação
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
    prompt_final = prompt_base + "\n" + formato_json

    try:
        response = client.models.generate_content(
            model=MODEL_FLASHCARD,
            contents=prompt_final,
            config={
                "temperature": 0.2, 
                "response_mime_type": "application/json"
            }
        )
        texto_limpo = limpar_json(response.text)
        dados = json.loads(texto_limpo)
        return dados.get("cards", [])
        
    except Exception as e:
        st.error(f"⚠️ Erro ao gerar Flashcard de Intervenção: {str(e)}")
        return []


def gerar_flashcard_sob_demanda(questao, pedido_usuario, api_key):
    """
    Gera um flashcard altamente focado baseado em um pedido específico do usuário.
    """
    client = genai.Client(api_key=api_key)
    
    edu_obj = questao.get("educational_objective", "")
    opcoes = "\n".join(questao.get("options", []))
    explanations = json.dumps(questao.get("explanations", {}), indent=2)

    prompt = f"""
You are an elite USMLE tutor. The student was reading the explanations for a question and realized they have a specific micro-gap in their knowledge.

QUESTION CONTEXT:
Objective: {edu_obj}
Options: {opcoes}
Explanations: {explanations}

STUDENT'S SPECIFIC REQUEST:
"{pedido_usuario}"

TASK:
Ignore the main objective of the question UNLESS it relates to the student's request. 
Focus PURELY on the STUDENT'S SPECIFIC REQUEST.
Generate 1 or 2 ATOMIC Q&A flashcards that answer their exact doubt.

STRICT SUPERMEMO RULES:
1. NO CLOZE DELETIONS. Use direct questions.
2. SHORT ANSWERS: 1 to 5 words max.
3. FOCUS ON MECHANISM, DIFFERENTIAL, OR DEFINITION (based on what they asked).

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
            config={
                "temperature": 0.2,
                "response_mime_type": "application/json"
            }
        )
        texto_limpo = limpar_json(response.text)
        dados = json.loads(texto_limpo)
        return dados.get("cards", [])
    except Exception as e:
        st.error(f"⚠️ Erro ao gerar Flashcard sob demanda: {str(e)}")
        return []
    
def gerar_mais_flashcards(questao, cards_atuais, api_key):
    """
    Gera flashcards adicionais explorando novos ângulos da mesma questão,
    evitando repetição do que já foi gerado no rascunho atual.
    """
    client = genai.Client(api_key=api_key)
    
    edu_obj = questao.get("educational_objective", "")
    
    # Formata os cards que já estão na tela para a IA não repeti-los
    if cards_atuais:
        cards_texto = "\n".join([f"- Q: {c.get('front')}\n  A: {c.get('back')}" for c in cards_atuais])
    else:
        cards_texto = "Nenhum card gerado ainda."

    prompt = f"""
You are an elite USMLE tutor. The student wants to explore THIS SAME TOPIC further to ensure absolute mastery.

EDUCATIONAL OBJECTIVE: {edu_obj}

CARDS ALREADY GENERATED (DO NOT REPEAT THESE CONCEPTS):
{cards_texto}

TASK:
Generate 1 or 2 NEW, ATOMIC Q&A flashcards exploring a DIFFERENT angle of the educational objective or the disease in question. 
For example, if the existing cards ask about the mechanism, you should ask about the diagnosis, classic clinical presentation, or gold-standard treatment.

STRICT SUPERMEMO RULES:
1. NO CLOZE DELETIONS. Direct questions only.
2. SHORT ANSWERS: 1 to 5 words max.
3. DIFFERENT ANGLE: You MUST NOT test the exact same fact already covered in the 'CARDS ALREADY GENERATED'.

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
            config={
                "temperature": 0.4, # Temperatura levemente maior para forçar a IA a ser mais criativa nos novos ângulos
                "response_mime_type": "application/json"
            }
        )
        texto_limpo = limpar_json(response.text)
        dados = json.loads(texto_limpo)
        return dados.get("cards", [])
    except Exception as e:
        st.error(f"⚠️ Erro ao expandir os flashcards: {str(e)}")
        return []