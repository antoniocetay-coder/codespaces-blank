"""Session state management, startup, and utility functions for USMLE app."""

import streamlit as st
import datetime
from db.core import get_conn, init_db
from db.questions import marcar_questao_respondida
from backup import criar_backup
from mastery import update_bkt


# ==============================================================================
# DATABASE & STARTUP
# ==============================================================================
@st.cache_resource
def _startup():
    init_db()


_startup()
criar_backup()


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def hoje_str():
    return now_utc().strftime("%Y-%m-%d")


# ==============================================================================
# SESSION STATE (Gerenciamento da Fila de Estudos)
# ==============================================================================
DEFAULTS = {
    "modo_estudo": None,
    "fila_estudo": [],
    "idx_atual": 0,
    "resposta_submetida": False,
    "letra_escolhida": None,
    "acertou_ultima": False,
    "confianca_escolhida": None,
    "tempo_inicio_questao": None,
    "tempo_gasto": None,
    "revelar_flashcard": False,
    "flashcards_rascunho": [],
    "flashcards_salvos": False,
    "checagem_feita": False,
    "resposta_tutor_atual": None,
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


def sair_do_modo_estudo():
    for k in DEFAULTS.keys():
        del st.session_state[k]
    st.session_state["flashcards_rascunho"] = []
    st.session_state["flashcards_salvos"] = False
    st.session_state["checagem_feita"] = False
    st.session_state["resposta_tutor_atual"] = None
    st.rerun()


def proximo_item_fila():
    st.session_state["idx_atual"] += 1
    st.session_state["resposta_submetida"] = False
    st.session_state["letra_escolhida"] = None
    st.session_state["revelar_flashcard"] = False
    st.session_state["tempo_inicio_questao"] = None
    st.session_state["confianca_escolhida"] = None
    st.session_state["tempo_gasto"] = None
    st.session_state["resposta_tutor_atual"] = None

    st.session_state["flashcards_rascunho"] = []
    st.session_state["flashcards_salvos"] = False
    st.session_state["checagem_feita"] = False
    st.rerun()


def salvar_resultado_pendente(q_id, sistema, is_correct, tags, time_taken, confidence):
    marcar_questao_respondida(q_id, is_correct, time_taken, confidence)
    conn = get_conn()

    for tag in tags:
        row = conn.execute(
            "SELECT correct, total, mastery_prob FROM tag_stats WHERE tag = ?",
            (tag,),
        ).fetchone()

        if row:
            curr_prob = row["mastery_prob"] if row["mastery_prob"] is not None else 0.15
            corrects = row["correct"] + int(is_correct)
            totals = row["total"] + 1
        else:
            curr_prob = 0.15
            corrects = int(is_correct)
            totals = 1

        new_prob = update_bkt(curr_prob, is_correct, confidence)

        conn.execute(
            """
            INSERT INTO tag_stats (tag, correct, total, mastery_prob) VALUES (?, ?, 1, ?)
            ON CONFLICT(tag) DO UPDATE SET
                correct = ?,
                total = ?,
                mastery_prob = ?
        """,
            (tag, corrects, new_prob, corrects, totals, new_prob),
        )

    if not is_correct:
        conn.execute(
            "UPDATE erros_por_sistema SET total = total + 1 WHERE sistema = ?",
            (sistema,),
        )

    conn.commit()
