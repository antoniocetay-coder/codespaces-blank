"""Tab 1: Study mode dispatcher — delegates to flashcard or question renderers."""

import streamlit as st

from ui.state import sair_do_modo_estudo
from ui.flashcard_renderer import render_flashcard
from ui.question_renderer import render_question


def render_study(api_key, dificuldade):
    fila = st.session_state["fila_estudo"]
    idx = st.session_state["idx_atual"]

    st.button("🔙 Sair e Voltar ao Dashboard", on_click=sair_do_modo_estudo)

    if idx >= len(fila):
        st.success("🎉 Sessão Concluída! Você destruiu a fila de hoje.")
        st.balloons()
        return

    item_atual = fila[idx]
    progresso = f"Progresso: {idx + 1} / {len(fila)}"
    st.progress((idx) / len(fila), text=progresso)

    if item_atual["type"] == "flashcard":
        render_flashcard(item_atual, api_key, dificuldade, fila, idx)
    elif item_atual["type"] == "question":
        render_question(item_atual, api_key, dificuldade)
