from config import *
from srs import *
from analytics import *
from database import *
from ai_engine import *
from backup import *
# ==============================================================================
# USMLE ECOls-SYSTEM V2
# Refatorado e melhorado
# ==============================================================================

import streamlit as st
from google import genai
import json
import uuid
import sqlite3
import pandas as pd
import datetime
# ==============================================================================
# DATABASE
# ==============================================================================

@st.cache_resource
@st.cache_resource
def startup():

    init_db()

@st.cache_resource
def startup():
    init_db()

startup()
criar_backup()

# ==============================================================================
# HELPERS
# ==============================================================================

def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)

def hoje_str():
    return now_utc().strftime("%Y-%m-%d")

# ==============================================================================
# SESSION STATE
# ==============================================================================

DEFAULTS = {
    "questao_atual": None,
    "resposta_submetida": False,
    "letra_escolhida": None,
    "acertou_ultima": False,
    "revelar_flashcard": False
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==============================================================================
# SM2
# ==============================================================================

def calcular_sm2(
    repetitions,
    interval,
    ease,
    quality
):

    if quality < 3:
        repetitions = 0
        interval = 1
        ease = max(1.3, ease - 0.2)

        return repetitions, interval, ease

    repetitions += 1

    if repetitions == 1:
        interval = 1

    elif repetitions == 2:
        interval = 6

    else:
        interval = round(interval * ease)

    ease = ease + (
        0.1 - (5 - quality) * (
            0.08 + (5 - quality) * 0.02
        )
    )

    ease = max(1.3, ease)

    return repetitions, interval, ease
# ==============================================================================
# DATABASE OPS
# ==============================================================================

def salvar_resultado(
    sistema,
    is_correct,
    questao,
    tags
):
    salvar_questao(
    sistema,
    dificuldade,
    q,
    correto
)



    conn = get_conn()

    conn.execute("""
        INSERT INTO historico
        VALUES (?, ?, ?, ?, ?)
    """, (
        str(uuid.uuid4()),
        json.dumps(questao),
        now_utc().isoformat(),
        sistema,
        int(is_correct)
    ))

    for tag in tags:

        conn.execute("""
            INSERT INTO tag_stats
            (tag, correct, total)

            VALUES (?, ?, 1)

            ON CONFLICT(tag)

            DO UPDATE SET

                correct = correct + excluded.correct,
                total = total + 1
        """, (
            tag,
            int(is_correct)
        ))

    if not is_correct:

        conn.execute("""
            UPDATE erros_por_sistema

            SET total = total + 1

            WHERE sistema = ?
        """, (sistema,))

    conn.commit()

def criar_flashcard_cloze(
    questao,
    sistema
):

    vignette = questao["vignette"]

    educational = questao["educational_objective"]

    correta = next(
        (
            o for o in questao["options"]
            if o.startswith(questao["correct"])
        ),
        ""
    )

    front = f"""
[{sistema}]

Clinical Pearl:

{vignette}

What is the key diagnosis/mechanism?
"""

    back = f"""
{correta}

Educational Objective:
{educational}
"""

    card = {
        "id": str(uuid.uuid4()),
        "front": front,
        "back": back,
        "next_review": hoje_str(),
        "interval": 1,
        "ease_factor": 2.5,
        "repetitions": 0,
        "lapses": 0,
        "sistema": sistema
    }

    conn = get_conn()

    conn.execute("""
        INSERT INTO flashcards
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        card["id"],
        card["front"],
        card["back"],
        card["next_review"],
        card["interval"],
        card["ease_factor"],
        card["repetitions"],
        card["lapses"],
        card["sistema"]
    ))

    conn.commit()

def get_cards_hoje():

    conn = get_conn()

    rows = conn.execute("""
        SELECT *
        FROM flashcards
        WHERE next_review <= ?
        ORDER BY next_review
    """, (hoje_str(),)).fetchall()

    return [dict(r) for r in rows]

# ==============================================================================
# UI
# ==============================================================================

with st.sidebar:

    st.header("Config")

    api_key = st.text_input(
        "Gemini API Key",
        type="password"
    )

    dificuldade = st.selectbox(
        "Difficulty",
        [
            "Easy",
            "Medium",
            "Hard",
            "Insane"
        ]
    )

st.title("USMLE ECO-SYSTEM V2")

tab1, tab2, tab3, tab4 = st.tabs([
    "QBank",
    "Anki",
    "Analytics",
    "History"
])

# ==============================================================================
# QBANK
# ==============================================================================

with tab1:

    sistema = st.selectbox(
        "Sistema",
        SISTEMAS_DISPONIVEIS
    )

    if st.button("Gerar Questão"):

        if not api_key:

            st.warning("API key.")

        else:

            with st.spinner("Gerando questão..."):

                q = gerar_questao(
                    sistema,
                    dificuldade,
                    api_key
                )

                if q:

                    st.session_state["questao_atual"] = q
                    st.session_state["resposta_submetida"] = False

                    st.rerun()

    q = st.session_state["questao_atual"]

    if q:

        st.subheader("Clinical Vignette")

        st.info(q["vignette"])

        escolha = st.radio(
            "Escolha:",
            q["options"],
            index=None,
            disabled=st.session_state["resposta_submetida"]
        )

        if not st.session_state["resposta_submetida"]:

            if st.button(
                "Submeter",
                disabled=(escolha is None)
            ):

                letra = escolha[0].upper()

                correto = (
                    letra == q["correct"]
                )

                st.session_state["resposta_submetida"] = True
                st.session_state["acertou_ultima"] = correto
                st.session_state["letra_escolhida"] = letra

                salvar_resultado(
                    sistema,
                    correto,
                    q,
                    q["content_tags"]
                )

                if not correto:

                    criar_flashcard_cloze(
                        q,
                        sistema
                    )

                st.rerun()

        if st.session_state["resposta_submetida"]:

            if st.session_state["acertou_ultima"]:

                st.success("Correto.")

            else:

                st.error(
                    f"Errado. Correta: {q['correct']}"
                )

            st.markdown("---")

            for opcao in q["options"]:

                letra = opcao[0]

                exp = q["explanations"].get(
                    letra,
                    ""
                )

                if letra == q["correct"]:

                    st.success(
                        f"{opcao}\n\n{exp}"
                    )

                else:

                    st.write(
                        f"{opcao}\n\n{exp}"
                    )

            st.markdown("---")

            st.info(
                q["educational_objective"]
            )

            st.caption(
                " | ".join(q["content_tags"])
            )

# ==============================================================================
# ANKI
# ==============================================================================

with tab2:

    cards = get_cards_hoje()

    st.metric(
        "Cards Hoje",
        len(cards)
    )

    if not cards:

        st.success("Deck zerado.")

    else:

        card = cards[0]

        st.subheader("Front")

        st.info(card["front"])

        if not st.session_state["revelar_flashcard"]:

            if st.button("Mostrar"):

                st.session_state["revelar_flashcard"] = True

                st.rerun()

        else:

            st.subheader("Back")

            st.success(card["back"])

            col1, col2, col3 = st.columns(3)

            qualities = [
                ("Again", 0),
                ("Hard", 3),
                ("Easy", 5)
            ]

            cols = [col1, col2, col3]

            for c, (label, quality) in zip(cols, qualities):

                with c:

                    if st.button(label):

                        reps, interval, ease = calcular_sm2(
                            card["repetitions"],
                            card["interval"],
                            card["ease_factor"],
                            quality
                        )

                        prox = (
                            now_utc() +
                            datetime.timedelta(days=interval)
                        ).strftime("%Y-%m-%d")

                        conn = get_conn()

                        conn.execute("""
                            UPDATE flashcards

                            SET
                                repetitions = ?,
                                interval = ?,
                                ease_factor = ?,
                                next_review = ?

                            WHERE id = ?
                        """, (
                            reps,
                            interval,
                            ease,
                            prox,
                            card["id"]
                        ))

                        conn.commit()

                        st.session_state["revelar_flashcard"] = False

                        st.rerun()

# ==============================================================================
# ANALYTICS
# ==============================================================================

with tab3:

    stats = get_tag_stats()

    st.subheader("Weak Areas")

    if not stats:

        st.info("Sem dados.")

    else:

        rows = []

        for tag, s in stats.items():

            pct = (
                s["correct"] / s["total"]
            ) * 100

            rows.append({
                "Tag": tag,
                "Accuracy": round(pct, 1),
                "Attempts": s["total"]
            })

        df = pd.DataFrame(rows)

        df = df.sort_values(
            "Accuracy"
        )

        st.dataframe(
            df,
            use_container_width=True
        )

        criticos = df[
            df["Accuracy"] < 50
        ]

        if not criticos.empty:

            st.error(
                "Critical weak concepts detected."
            )

            for _, row in criticos.iterrows():

                st.write(
                    f"- {row['Tag']} "
                    f"({row['Accuracy']}%)"
                )
                # ==============================================================================
# HISTORY
# ==============================================================================

with tab4:

    st.header("Question History")

    questions = get_questions()

    if not questions:

        st.info("No questions answered yet.")

    else:

        filtro_sistema = st.selectbox(
            "Filter by system",
            ["Todos"] + SISTEMAS_DISPONIVEIS
        )

        if filtro_sistema != "Todos":

            questions = [
                q for q in questions
                if q["sistema"] == filtro_sistema
            ]

        st.write(f"Questions found: {len(questions)}")

        st.markdown("---")

        for q in questions:

            acertou = "✅" if q["answered_correctly"] else "❌"

            with st.expander(
                f"{acertou} | {q['sistema']} | {q['dificuldade']}"
            ):

                st.caption(q["created_at"])

                st.markdown("### Tags")

                try:

                    tags = json.loads(q["tags"])

                    st.write(" | ".join(tags))

                except:
                    st.write(q["tags"])

                st.markdown("---")

                try:

                    question_data = json.loads(
                        q["question_json"]
                    )

                    st.markdown("### Vignette")

                    st.info(
                        question_data["vignette"]
                    )

                    st.markdown("### Options")

                    for option in question_data["options"]:

                        if option.startswith(
                            question_data["correct"]
                        ):

                            st.success(option)

                        else:

                            st.write(option)

                    st.markdown("---")

                    st.markdown("### Educational Objective")

                    st.warning(
                        question_data[
                            "educational_objective"
                        ]
                    )

                except Exception as e:

                    st.error(
                        f"Error loading question: {e}"
                    )