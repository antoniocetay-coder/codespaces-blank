"""Flashcard forge — generate and approve AI flashcards from question results."""

import streamlit as st

from db.flashcards import get_flashcards_by_tags, salvar_flashcard_db
from flashcard_engine import (
    orquestrar_flashcards,
    gerar_mais_flashcards,
    gerar_flashcard_sob_demanda,
)


def render_forge_panel(q, q_db, api_key):
    st.markdown("---")
    st.markdown("### 🛠️ Forja de Flashcards")

    cards_banco_atual = get_flashcards_by_tags(q["content_tags"])

    col_btn_erro, col_btn_mais = st.columns(2)

    with col_btn_erro:
        if st.button("💡 Analisar meu Erro/Chute", use_container_width=True):
            with st.spinner("Analisando seu viés e checando banco de cards..."):
                rascunhos_tela = st.session_state.get("flashcards_rascunho", [])
                cards_ia = orquestrar_flashcards(
                    q,
                    st.session_state["letra_escolhida"],
                    st.session_state["acertou_ultima"],
                    st.session_state["confianca_escolhida"],
                    cards_banco_atual,
                    rascunhos_tela,
                    api_key,
                )
                if cards_ia:
                    if "flashcards_rascunho" not in st.session_state:
                        st.session_state["flashcards_rascunho"] = []
                    st.session_state["flashcards_rascunho"].extend(cards_ia)
                    st.rerun()

    with col_btn_mais:
        if st.button("➕ Explorar Outros Ângulos", use_container_width=True):
            with st.spinner("Buscando novos ângulos da doença..."):
                rascunhos_tela = st.session_state.get("flashcards_rascunho", [])
                novos_cards = gerar_mais_flashcards(
                    q, cards_banco_atual, rascunhos_tela, api_key,
                )
                if novos_cards:
                    if "flashcards_rascunho" not in st.session_state:
                        st.session_state["flashcards_rascunho"] = []
                    st.session_state["flashcards_rascunho"].extend(novos_cards)
                    st.rerun()

    st.write("")
    col_input, col_btn_especifico = st.columns([3, 1])
    with col_input:
        pedido_customizado = st.text_input(
            "Lacuna Específica",
            placeholder="Ex: Fisiopatologia da alternativa C",
            label_visibility="collapsed",
        )
    with col_btn_especifico:
        if st.button("🎯 Gerar Específico", use_container_width=True):
            if pedido_customizado:
                with st.spinner("Forjando card sob demanda..."):
                    rascunhos_tela = st.session_state.get("flashcards_rascunho", [])
                    novos_cards = gerar_flashcard_sob_demanda(
                        q, pedido_customizado, cards_banco_atual,
                        rascunhos_tela, api_key,
                    )
                    if novos_cards:
                        if "flashcards_rascunho" not in st.session_state:
                            st.session_state["flashcards_rascunho"] = []
                        st.session_state["flashcards_rascunho"].extend(novos_cards)
                        st.rerun()
            else:
                st.warning("Digite algo ao lado.")

    render_draft_approval(q, q_db)


def render_draft_approval(q, q_db):
    if st.session_state.get("flashcards_salvos", False):
        st.success("✅ Cards salvos no Baralho!")
        return

    rascunhos = st.session_state.get("flashcards_rascunho", [])
    if len(rascunhos) == 0:
        return

    st.markdown("---")
    chave_unica = f"form_{q_db['id']}"
    with st.form(key=chave_unica):
        editados = []
        for i, card in enumerate(rascunhos):
            st.write(f"**Card {i+1}**")
            key_front = f"f_{i}_{q_db['id']}"
            key_back = f"b_{i}_{q_db['id']}"
            novo_front = st.text_area(
                "Q (Front)", value=card.get("front", ""), key=key_front
            )
            novo_back = st.text_area(
                "A (Back)", value=card.get("back", ""), key=key_back
            )
            editados.append({
                "front": novo_front,
                "back": novo_back,
                "tags": card.get("tags", q["content_tags"]),
            })

        if st.form_submit_button("Aprovar e Salvar Todos"):
            for c in editados:
                salvar_flashcard_db(
                    c["front"], c["back"], q_db["sistema"], c["tags"],
                )
            st.session_state["flashcards_salvos"] = True
            st.rerun()
