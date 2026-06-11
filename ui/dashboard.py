"""Tab 1: Dashboard — planning and study mode selection."""

import streamlit as st
from db.flashcards import get_cards_hoje
from db.questions import get_pending_questions
from scheduler import montar_fila_estudo, gerar_planos_estudo, gerar_lote_background


def render_dashboard(api_key, dificuldade):
    if st.session_state["modo_estudo"] is not None:
        return  # study mode is active; handled by study.py

    cards_hoje = get_cards_hoje()
    questoes_pendentes = get_pending_questions()

    col1, col2 = st.columns(2)
    col1.metric("🃏 Flashcards Vencidos", len(cards_hoje))
    col2.metric("📝 Questões na Fila", len(questoes_pendentes))

    st.markdown("---")
    st.subheader("1. Planejamento Semanal & Preparação")

    qtd_gerar = st.slider(
        "Quantas questões deseja gerar neste lote?",
        min_value=1, max_value=10, value=3,
    )

    planos = gerar_planos_estudo()

    c_box1, c_box2, c_box3 = st.columns(3)
    gerando_agora = False

    for col, plano, i in zip([c_box1, c_box2, c_box3], planos, range(3)):
        with col:
            with st.container(border=True):
                st.markdown(f"**{plano['titulo']}**")
                for s in plano['sistemas']:
                    st.write(f"- {s}")

                st.write("")

                if st.button(
                    f"Gerar Plano {i+1}", use_container_width=True,
                    key=f"btn_plano_{i}",
                ):
                    gerando_agora = True
                    if not api_key:
                        st.error("API Key necessária.")
                    else:
                        with st.spinner(
                            f"Gerando {qtd_gerar} questões para "
                            f"{', '.join(plano['sistemas'])}..."
                        ):
                            sucessos = gerar_lote_background(
                                plano['sistemas'], dificuldade, api_key,
                                qtd_questoes=qtd_gerar,
                            )
                            st.success(f"{sucessos} Questões geradas!")
                            st.rerun()

    st.markdown("---")
    st.subheader("2. Escolha seu Modo de Estudo de Hoje")

    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button(
            "🔋 Review Mode\n(Apenas Anki)", use_container_width=True,
            disabled=gerando_agora,
        ):
            st.session_state["modo_estudo"] = "Review"
            st.session_state["fila_estudo"] = montar_fila_estudo("Review")
            st.rerun()
    with c2:
        if st.button(
            "⚡ QBank Mode\n(Apenas Questões)", use_container_width=True,
            disabled=gerando_agora,
        ):
            st.session_state["modo_estudo"] = "QBank"
            st.session_state["fila_estudo"] = montar_fila_estudo("QBank")
            st.rerun()
    with c3:
        if st.button(
            "🧠 Interleaved Mode\n(O Super Deck)", use_container_width=True,
            disabled=gerando_agora,
        ):
            st.session_state["modo_estudo"] = "Interleaved"
            st.session_state["fila_estudo"] = montar_fila_estudo("Interleaved")
            st.rerun()
