"""Tab 2: Targeted Practice (Brute Force Mode)."""

import streamlit as st
from config import SISTEMAS_DISPONIVEIS
from taxonomy import TAXONOMIA_COMPLETA
from ai_engine import gerar_questao
from db.questions import salvar_questao


def render_targeted(api_key, dificuldade):
    st.header("🎯 Prática Focada (Brute Force)")
    st.write(
        "Véspera de prova? Escolha uma tag específica e force "
        "a geração ignorando o Cooldown."
    )

    sys_brute = st.selectbox("Sistema:", SISTEMAS_DISPONIVEIS, key="sys_brute")
    tax_brute = TAXONOMIA_COMPLETA.get(sys_brute, {})
    todas_tags_brute = []
    for tags_l in tax_brute.values():
        if isinstance(tags_l, list):
            todas_tags_brute.extend(tags_l)

    tag_alvo = st.selectbox("Tag Alvo:", sorted(todas_tags_brute))

    if st.button("Gerar Questão Focada 🚀"):
        if not api_key:
            st.error("API Key necessária.")
        else:
            with st.spinner(f"Gerando questão focada em {tag_alvo}..."):
                q_brute = gerar_questao(
                    sys_brute, dificuldade, api_key, tags_alvo=[tag_alvo]
                )
                if q_brute:
                    salvar_questao(
                        sys_brute, dificuldade, q_brute, False,
                        q_brute["content_tags"], status="answered",
                    )
                    st.success("Questão gerada e salva no seu Histórico!")
                    with st.expander("Ver Questão Gerada", expanded=True):
                        st.info(q_brute["vignette"])
                        for opt in q_brute["options"]:
                            st.write(opt)
                        st.success(f"Correta: {q_brute['correct']}")
