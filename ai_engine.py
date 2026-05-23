import json
import streamlit as st

from google import genai

from config import *
from analytics import *

def limpar_json(texto):


    texto = texto.strip().lstrip("\ufeff")

    if "```" in texto:
        linhas = texto.splitlines()
        linhas = [
            l for l in linhas
            if not l.strip().startswith("```")
        ]
        texto = "\n".join(linhas)

    inicio = texto.find("{")
    fim = texto.rfind("}")

    if inicio != -1 and fim != -1:
        texto = texto[inicio:fim+1]

    return texto

def validar_questao(q):

    if not isinstance(q, dict):
        return False

    faltando = SCHEMA_OBRIGATORIO - q.keys()

    if faltando:
        return False

    return True

# ==============================================================================
# AI ENGINE
# ==============================================================================

def gerar_prompt(
    sistema,
    dificuldade,
    weak_tags
):

    weak_text = ", ".join(weak_tags)

    return f"""
You are an elite NBME-style USMLE question writer.

Generate ONE high-quality USMLE clinical vignette.

SYSTEM:
{sistema}

DIFFICULTY:
{dificuldade}

FOCUS WEAK AREAS:
{weak_text}

STRICT REQUIREMENTS:

- NBME style
- realistic clinical reasoning
- plausible distractors
- no giveaway buzzwords
- mechanism-based
- board-level integration
- single best answer
- concise but difficult
- integrate physiology, pathology and pharmacology

Return ONLY valid JSON.

{{
    "vignette": "...",

    "options": [
        "A) ...",
        "B) ...",
        "C) ...",
        "D) ..."
    ],

    "correct": "A",

    "explanations": {{
        "A": "...",
        "B": "...",
        "C": "...",
        "D": "..."
    }},

    "educational_objective": "...",

    "content_tags": [
        "tag1",
        "tag2"
    ]
    "taxonomy": {{
  "system": "Renal",
  "topic": "Acid/Base",
  "subtopic": "Type 4 RTA"
    }}
}}
"""

def gerar_questao(
    sistema,
    dificuldade,
    api_key
):

    weak_tags = get_weak_tags()

    client = genai.Client(api_key=api_key)

    prompt = gerar_prompt(
        sistema,
        dificuldade,
        weak_tags
    )

    try:

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={
                "temperature": 0.4
            }
        )

        texto = limpar_json(response.text)

        questao = json.loads(texto)

        if not validar_questao(questao):

            st.error("JSON inválido.")

            with st.expander("Resposta IA"):
                st.code(texto)

            return None

        questao["correct"] = (
            questao["correct"]
            .strip()
            .upper()[0]
        )

        return questao

    except Exception as e:

        st.error(str(e))

        return None
SCHEMA_OBRIGATORIO = {
    "vignette",
    "options",
    "correct",
    "explanations",
    "educational_objective",
    "content_tags"
}