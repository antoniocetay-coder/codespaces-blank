"""Tutor AI panel — ask questions and generate flashcards from explanations."""

import streamlit as st
import time

from db.flashcards import salvar_flashcard_db
from ai_engine import explicar_duvida_tutor
from flashcard_engine import gerar_flashcards_do_tutor


def render_tutor_ai(card, api_key):
    st.markdown("### 🧑‍🏫 Tutor AI")
    col_tutor_input, col_tutor_btn = st.columns([4, 1])

    with col_tutor_input:
        duvida_tutor = st.text_input(
            "Dúvida",
            placeholder="Não entendeu o card? Peça uma explicação...",
            label_visibility="collapsed",
            key=f"input_tutor_{card['id']}",
        )

    with col_tutor_btn:
        clicou_perguntar = st.button(
            "🗣️ Perguntar", use_container_width=True,
            key=f"btn_tutor_{card['id']}",
        )

    if clicou_perguntar:
        if not api_key:
            st.error("API Key necessária.")
        elif not duvida_tutor:
            st.warning("Digite uma dúvida.")
        else:
            with st.spinner("O Tutor está digitando..."):
                contexto = f"Front: {card['front']}\nBack: {card['back']}"
                resposta = explicar_duvida_tutor(contexto, duvida_tutor, api_key)
                st.session_state["resposta_tutor_atual"] = resposta

    if st.session_state["resposta_tutor_atual"]:
        st.info(st.session_state["resposta_tutor_atual"])
        if st.button(
            "⚡ Transformar Explicação em Flashcard",
            key=f"btn_transf_{card['id']}",
        ):
            with st.spinner("Forjando novo card..."):
                cards_tela = [card]
                rascunhos_tela = st.session_state.get("flashcards_rascunho", [])
                novos_cards = gerar_flashcards_do_tutor(
                    st.session_state["resposta_tutor_atual"],
                    cards_tela,
                    rascunhos_tela,
                    api_key,
                )
                if novos_cards:
                    st.session_state["flashcards_rascunho"].extend(novos_cards)
                    st.rerun()

    rascunhos = st.session_state.get("flashcards_rascunho", [])
    if len(rascunhos) > 0:
        st.markdown("---")
        chave_unica = f"form_tutor_{card['id']}"
        with st.form(key=chave_unica):
            editados = []
            for i, c_rascunho in enumerate(rascunhos):
                st.write(f"**Card {i+1} (Expansão do Tutor)**")
                key_front = f"tf_{i}_{card['id']}"
                key_back = f"tb_{i}_{card['id']}"
                novo_front = st.text_area(
                    "Q (Front)", value=c_rascunho.get("front", ""), key=key_front
                )
                novo_back = st.text_area(
                    "A (Back)", value=c_rascunho.get("back", ""), key=key_back
                )
                editados.append({
                    "front": novo_front,
                    "back": novo_back,
                    "tags": ["Tutor_Expansion"],
                })

            if st.form_submit_button("Aprovar e Salvar Todos"):
                for c in editados:
                    salvar_flashcard_db(
                        c["front"], c["back"],
                        card.get("sistema", "General"), c["tags"],
                    )
                st.session_state["flashcards_rascunho"] = []
                st.success("✅ Card do Tutor Salvo!")
                time.sleep(1)
                st.rerun()
