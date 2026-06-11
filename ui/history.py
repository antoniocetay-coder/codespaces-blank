"""Tab 4: Question History."""

import json
import streamlit as st
from config import SISTEMAS_DISPONIVEIS
from db.questions import get_questions


def render_history():
    st.header("Question History")
    questions = get_questions()

    if not questions:
        st.info("No questions answered yet.")
        return

    filtro_sistema = st.selectbox(
        "Filter by system", ["Todos"] + SISTEMAS_DISPONIVEIS
    )
    if filtro_sistema != "Todos":
        questions = [q for q in questions if q["sistema"] == filtro_sistema]

    st.write(f"Questions found: {len(questions)}")
    for q in questions:
        acertou = "✅" if q["answered_correctly"] else "❌"
        with st.expander(f"{acertou} | {q['sistema']} | {q['dificuldade']}"):
            st.caption(q["created_at"])
            if q.get("tag_list"):
                st.write(" | ".join(q["tag_list"].split("|")))
            else:
                st.write("Sem tags")
            st.markdown("---")
            try:
                q_data = json.loads(q["question_json"])
                st.info(q_data["vignette"])
                for option in q_data["options"]:
                    if option.startswith(q_data["correct"]):
                        st.success(option)
                    else:
                        st.write(option)
                st.warning(q_data["educational_objective"])
            except Exception:
                st.error("Error loading question.")
