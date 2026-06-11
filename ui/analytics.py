"""Tab 3: Analytics — Performance Cockpit."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from db.core import get_conn
from db.confusions import get_global_confusions
from analytics import get_system_stats, get_metacognition_stats, get_time_stats, get_fsrs_forecast
from mastery import classify_tag_bkt
from ui.state import now_utc


def render_analytics():
    st.header("📊 Cockpit de Performance USMLE")

    sys_stats = get_system_stats()
    meta_stats = get_metacognition_stats()
    time_stats = get_time_stats()
    fsrs_data = get_fsrs_forecast()
    confusions = get_global_confusions()

    # --- System Radar ---
    if sys_stats:
        df_sys = pd.DataFrame(sys_stats)
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=df_sys["avg_pct"].tolist(),
            theta=df_sys["sistema"].tolist(),
            fill="toself",
            name="Performance por Sistema",
        ))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            showlegend=False,
        )
        st.plotly_chart(fig_radar, use_container_width=True)
    else:
        st.info("Responda algumas questões para ver o gráfico de performance.")

    # --- Metacognition ---
    st.markdown("---")
    col_meta, col_tempo = st.columns(2)

    with col_meta:
        st.subheader("🎯 Metacognition (Confiança vs Acerto)")
        if meta_stats:
            df_meta = pd.DataFrame(meta_stats)
            if not df_meta.empty:
                fig_meta = px.bar(
                    df_meta, x="confidence", y=["total", "correct"],
                    barmode="group",
                    labels={"value": "Questões", "confidence": "Confiança"},
                    color_discrete_map={"total": "#636EFA", "correct": "#28a745"},
                )
                st.plotly_chart(fig_meta, use_container_width=True)
            else:
                st.caption("Sem dados de metacognição ainda.")
        else:
            st.caption("Sem dados de metacognição ainda.")

    # --- Time stats ---
    with col_tempo:
        st.subheader("⏱️ Tempo Médio por Sistema")
        if time_stats:
            df_time = pd.DataFrame(time_stats)
            df_time["Resultado"] = df_time["answered_correctly"].apply(
                lambda x: "Acertou" if x == 1 else "Errou"
            )
            fig_time = px.bar(
                df_time, x="avg_time", y="sistema", color="Resultado",
                orientation="h", barmode="group",
                color_discrete_map={"Acertou": "#28a745", "Errou": "#dc3545"},
                labels={"avg_time": "Tempo Médio (s)", "sistema": "Sistema"},
            )
            fig_time.add_vline(
                x=90, line_width=2, line_dash="dash", line_color="red",
                annotation_text="USMLE Limit (90s)",
            )
            st.plotly_chart(fig_time, use_container_width=True)
        else:
            st.caption("Sem dados de tempo registrados ainda.")

    # --- FSRS Forecast + Confusions ---
    st.markdown("---")
    col_fsrs, col_conf = st.columns(2)

    with col_fsrs:
        st.subheader("📅 Forecast de Revisões (FSRS)")
        if fsrs_data:
            df_fsrs = pd.DataFrame(fsrs_data)
            df_fsrs["due"] = pd.to_datetime(df_fsrs["due"])
            df_fsrs = df_fsrs[df_fsrs["due"].dt.date >= now_utc().date()]

            if not df_fsrs.empty:
                df_fsrs["due_str"] = df_fsrs["due"].dt.strftime("%d/%m")
                fig_fsrs = px.bar(
                    df_fsrs, x="due_str", y="qtd",
                    labels={"due_str": "Data", "qtd": "Flashcards Agendados"},
                    color_discrete_sequence=["#636EFA"],
                )
                st.plotly_chart(fig_fsrs, use_container_width=True)
            else:
                st.caption("Nenhum card agendado para o futuro.")
        else:
            st.caption("Sem dados do FSRS.")

    with col_conf:
        st.subheader("🪤 Top Armadilhas (Red Herrings)")
        if confusions:
            df_conf = pd.DataFrame(confusions)
            st.dataframe(
                df_conf.rename(columns={
                    "tag_correct": "O que era (Verdadeiro)",
                    "tag_confused": "O que você achou (Falso)",
                    "count": "Vezes que caiu",
                }),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.success(
                "Você ainda não caiu em nenhum distrator de forma repetida!"
            )

    # --- BKT Mastery ---
    st.markdown("---")
    with st.expander("Ver Domínio BKT Completo por Micro-Tags"):
        conn = get_conn()
        rows_db = conn.execute(
            "SELECT tag, correct, total, mastery_prob FROM tag_stats"
        ).fetchall()

        rows = []
        for r in rows_db:
            if r["total"] > 0:
                prob = (
                    r["mastery_prob"]
                    if r["mastery_prob"] is not None
                    else (r["correct"] / r["total"])
                )
                pct_bkt = prob * 100
                nivel_dominio = classify_tag_bkt(prob).value

                rows.append({
                    "Tag": r["tag"],
                    "BKT Mastery (%)": round(pct_bkt, 1),
                    "Attempts": r["total"],
                    "Status": nivel_dominio.upper(),
                })

        if rows:
            df_tags = pd.DataFrame(rows).sort_values("BKT Mastery (%)")
            st.dataframe(df_tags, use_container_width=True, hide_index=True)
