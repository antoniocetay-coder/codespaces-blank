"""Question rendering — prompt, result display, and forge panel integration."""

import streamlit as st
import json
import time

from db.confusions import registrar_confusao
from ui.state import (
    salvar_resultado_pendente,
    proximo_item_fila,
)
from ui.forge_panel import render_forge_panel


def render_question(item_atual, api_key, dificuldade):
    q_db = item_atual["item"]
    q = json.loads(q_db["question_json"])

    if not st.session_state["resposta_submetida"]:
        show_question_prompt(q, q_db)
    else:
        show_question_result(q, q_db, api_key)


def show_question_prompt(q, q_db):
    st.markdown("## 📝 Questão")
    st.info(q["vignette"])

    options_display = "\n\n".join(q["options"])
    st.write(options_display)

    st.session_state["tempo_inicio_questao"] = (
        st.session_state.get("tempo_inicio_questao") or time.time()
    )

    st.markdown("### Sua Resposta")
    confianca = st.radio(
        "Nível de Confiança:",
        ["Confirmei", "Meio na Dúvida", "Chute Cego"],
        horizontal=True,
        key=f"conf_{q_db['id']}",
    )

    escolha = st.radio(
        "Alternativas:",
        q["options"],
        index=None,
        key=f"opt_{q_db['id']}",
    )

    if escolha and st.button("Confirmar Resposta", type="primary"):
        tempo_gasto = int(time.time() - st.session_state["tempo_inicio_questao"])
        letra = escolha[0].upper()
        correto = letra == q["correct"]

        st.session_state["resposta_submetida"] = True
        st.session_state["acertou_ultima"] = correto
        st.session_state["letra_escolhida"] = letra
        st.session_state["confianca_escolhida"] = confianca
        st.session_state["tempo_gasto"] = tempo_gasto

        salvar_resultado_pendente(
            q_db["id"], q_db["sistema"], correto,
            q["content_tags"], tempo_gasto, confianca,
        )

        if not correto and confianca != "Chute Cego":
            dist_tags = q.get("distractor_tags", {})
            tag_correta = dist_tags.get(q["correct"])
            tag_errada = dist_tags.get(letra)
            if tag_correta and tag_errada:
                registrar_confusao(tag_correta, tag_errada)

        st.rerun()


def show_question_result(q, q_db, api_key):
    t_gasto = st.session_state["tempo_gasto"]
    if st.session_state["acertou_ultima"]:
        if st.session_state["confianca_escolhida"] == "Chute Cego":
            st.warning(f"⚠️ Correto, mas foi um Chute Cego! (Tempo: {t_gasto}s)")
        else:
            st.success(f"✅ Correto! (Tempo: {t_gasto}s)")
    else:
        st.error(f"❌ Errado. Correta: {q['correct']} (Tempo: {t_gasto}s)")

    if t_gasto > 90:
        st.caption("⏱️ *Aviso: Você passou da marca de 90 segundos do USMLE.*")

    st.markdown("---")
    for opcao in q["options"]:
        letra = opcao[0]
        exp = q["explanations"].get(letra, "")
        if letra == q["correct"]:
            st.success(f"{opcao}\n\n{exp}")
        else:
            st.write(f"{opcao}\n\n{exp}")

    st.info(f"**Educational Objective:**\n{q['educational_objective']}")
    st.caption(" | ".join(q["content_tags"]))

    render_forge_panel(q, q_db, api_key)

    st.markdown("---")
    if st.button("Próximo Item ➡️", use_container_width=True, type="primary"):
        proximo_item_fila()
