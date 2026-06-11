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
    texto_banco = (
        "\n".join(
            f"- Q: {c.get('front')} | A: {c.get('back')}" for c in cards_banco
        )
        if cards_banco
        else "None"
    )
    texto_rascunho = (
        "\n".join(
            f"- Q: {c.get('front')} | A: {c.get('back')}" for c in cards_rascunho
        )
        if cards_rascunho
        else "None"
    )

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
