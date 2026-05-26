from config import *
from fsrs import *
from sd import process_sd
from mastery import classify_tag
from analytics import *
from database import *
from ai_engine import *
from backup import *

import streamlit as st
from google import genai
import json
import uuid
import pandas as pd
import datetime

# ==============================================================================
# DATABASE
# ==============================================================================

@st.cache_resource
def startup():
    init_db()

startup()
criar_backup()

def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)

def hoje_str():
    return now_utc().strftime("%Y-%m-%d")

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
# DATABASE OPS
# ==============================================================================

def salvar_resultado(sistema, dificuldade, is_correct, questao, tags):
    salvar_questao(sistema, dificuldade, questao, is_correct, tags)
    conn = get_conn()

    for tag in tags:
        conn.execute("""
            INSERT INTO tag_stats (tag, correct, total) VALUES (?, ?, 1)
            ON CONFLICT(tag) DO UPDATE SET correct = correct + excluded.correct, total = total + 1
        """, (tag, int(is_correct)))

    if not is_correct:
        conn.execute("UPDATE erros_por_sistema SET total = total + 1 WHERE sistema = ?", (sistema,))

    conn.commit()

def salvar_flashcard_db(front, back, sistema, tags):
    # Função nova e enxuta, apenas para salvar no banco!
    card_id = str(uuid.uuid4())
    conn = get_conn()
    
    conn.execute("INSERT INTO flashcards (id, front, back, sistema) VALUES (?, ?, ?, ?)", 
                 (card_id, front, back, sistema))

    conn.execute("INSERT INTO srs_state (object_id, object_type, due, last_review) VALUES (?, ?, ?, ?)", 
                 (card_id, ItemType.FLASHCARD.value, hoje_str(), hoje_str()))
    
    for tag in tags:
        conn.execute("INSERT INTO item_tags (object_id, object_type, tag) VALUES (?, ?, ?)", 
                     (card_id, ItemType.FLASHCARD.value, tag))
        
    conn.commit()

def get_cards_hoje():
    conn = get_conn()
    rows = conn.execute("""
        SELECT f.id, f.front, f.back, f.sistema, 
               s.stability, s.difficulty, s.due, s.repetitions, s.lapses, s.last_review
        FROM flashcards f
        JOIN srs_state s ON f.id = s.object_id
        WHERE s.object_type = ? AND s.due <= ?
        ORDER BY s.due ASC
    """, (ItemType.FLASHCARD.value, hoje_str())).fetchall()
    return [dict(r) for r in rows]

# ==============================================================================
# UI
# ==============================================================================

with st.sidebar:
    st.header("Config")
    try:
        chave_salva = st.secrets.get("GEMINI_API_KEY", "")
    except:
        chave_salva = ""

    api_key = st.text_input("Gemini API Key", value=chave_salva, type="password")
    dificuldade = st.selectbox("Difficulty", ["Easy", "Medium", "Hard", "Insane"])

st.title("USMLE ECO-SYSTEM V2")

tab1, tab2, tab3, tab4 = st.tabs(["QBank", "Anki", "Analytics", "History"])

# ==============================================================================
# QBANK (Com Flashcards Inteligentes)
# ==============================================================================

with tab1:
    sistema = st.selectbox("Sistema", SISTEMAS_DISPONIVEIS)

    if st.button("Gerar Questão"):
        if not api_key:
            st.warning("API key necessária.")
        else:
            with st.spinner("Gerando questão..."):
                q = gerar_questao(sistema, dificuldade, api_key)
                if q:
                    st.session_state["questao_atual"] = q
                    st.session_state["resposta_submetida"] = False
                    
                    # Limpa os rascunhos de flashcard da questão anterior
                    if "flashcards_rascunho" in st.session_state:
                        del st.session_state["flashcards_rascunho"]
                    if "flashcards_salvos" in st.session_state:
                        del st.session_state["flashcards_salvos"]
                        
                    st.rerun()

    q = st.session_state["questao_atual"]

    if q:
        st.subheader("Clinical Vignette")
        st.info(q["vignette"])

        escolha = st.radio("Escolha:", q["options"], index=None, disabled=st.session_state["resposta_submetida"])

        if not st.session_state["resposta_submetida"]:
            if st.button("Submeter", disabled=(escolha is None)):
                letra = escolha[0].upper()
                correto = (letra == q["correct"])

                st.session_state["resposta_submetida"] = True
                st.session_state["acertou_ultima"] = correto
                st.session_state["letra_escolhida"] = letra

                salvar_resultado(sistema, dificuldade, correto, q, q["content_tags"])
                st.rerun()

        if st.session_state["resposta_submetida"]:
            if st.session_state["acertou_ultima"]:
                st.success("Correto.")
            else:
                st.error(f"Errado. Correta: {q['correct']}")

            st.markdown("---")
            for opcao in q["options"]:
                letra = opcao[0]
                exp = q["explanations"].get(letra, "")
                if letra == q["correct"]:
                    st.success(f"{opcao}\n\n{exp}")
                else:
                    st.write(f"{opcao}\n\n{exp}")

            st.markdown("---")
            st.info(q["educational_objective"])
            st.caption(" | ".join(q["content_tags"]))

            # --- FLUXO DO FLASHCARD INTELIGENTE ---
            # --- FLUXO DO FLASHCARD INTELIGENTE ---
            if not st.session_state["acertou_ultima"]:
                st.markdown("---")
                st.markdown("### 💡 Flashcards Inteligentes")
                
                if st.session_state.get("flashcards_salvos", False):
                    st.success("✅ Cards aprovados e salvos no seu Baralho FSRS!")
                else:
                    # Se ainda não gerou o rascunho, a IA gera agora
                    if "flashcards_rascunho" not in st.session_state:
                        with st.spinner("A IA está analisando seu erro e checando seu Baralho para evitar duplicatas..."):
                            
                            # 1. Puxa os cards que você já tem dessas tags
                            cards_existentes = get_flashcards_by_tags(q["content_tags"])
                            
                            # 2. Manda pra IA avaliar
                            cards_ia = gerar_flashcards_ia(q, st.session_state["letra_escolhida"], cards_existentes, api_key)
                            
                            st.session_state["flashcards_rascunho"] = cards_ia
                            st.session_state["checagem_feita"] = True
                            st.rerun()

                    rascunhos = st.session_state.get("flashcards_rascunho", [])
                    checagem = st.session_state.get("checagem_feita", False)
                    
                    if rascunhos:
                        st.info("Revise e edite os cards antes de enviar para o FSRS:")
                        
                        # CRIAMOS UMA CHAVE ÚNICA BASEADA NA QUESTÃO PARA O STREAMLIT NÃO TRAVAR
                        chave_unica = abs(hash(q["vignette"]))
                        
                        with st.form(key=f"form_flashcards_{chave_unica}"):
                            editados = []
                            for i, card in enumerate(rascunhos):
                                st.write(f"**Card {i+1}**")
                                novo_front = st.text_area("Front", value=card.get("front", ""), key=f"front_{i}_{chave_unica}")
                                novo_back = st.text_area("Back", value=card.get("back", ""), key=f"back_{i}_{chave_unica}")
                                editados.append({"front": novo_front, "back": novo_back, "tags": card.get("tags", q["content_tags"])})
                                st.markdown("---")
                            
                            if st.form_submit_button("Aprovar e Salvar no Baralho"):
                                for c in editados:
                                    salvar_flashcard_db(c["front"], c["back"], sistema, c["tags"])
                                st.session_state["flashcards_salvos"] = True
                                st.rerun()
                                
                    elif checagem:
                        st.success("✨ A IA verificou o seu Baralho e concluiu que você já possui flashcards que cobrem perfeitamente este erro. Nenhuma duplicata foi gerada!")

# ==============================================================================
# ANKI
# ==============================================================================

with tab2:
    cards = get_cards_hoje()
    st.metric("Cards Hoje", len(cards))

    if not cards:
        st.success("Deck zerado. Volte amanhã!")
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

            hoje_data = now_utc().date()
            try:
                last_rev_data = datetime.datetime.strptime(card["last_review"], "%Y-%m-%d").date()
                elapsed_days = (hoje_data - last_rev_data).days
            except:
                elapsed_days = 0

            st.markdown("### 🧠 Saúde da Memória (sd.py)")
            estado_memoria = process_sd(card["stability"], card["difficulty"], max(0, elapsed_days))
            st.json(estado_memoria)
            st.markdown("---")

            st.write("Avalie sua resposta:")
            col1, col2, col3, col4 = st.columns(4)

            qualities = [("Again", 1, col1), ("Hard", 2, col2), ("Good", 3, col3), ("Easy", 4, col4)]

            for label, grade, col in qualities:
                with col:
                    if st.button(label, use_container_width=True):
                        d, s, r, interval, reps, lapses = calcular_fsrs(
                            grade, card["difficulty"], card["stability"],
                            max(0, elapsed_days), card["repetitions"], card["lapses"]
                        )
                        prox = (now_utc() + datetime.timedelta(days=interval)).strftime("%Y-%m-%d")

                        conn = get_conn()
                        conn.execute("""
                            UPDATE srs_state
                            SET repetitions=?, stability=?, difficulty=?, last_review=?, due=?, lapses=?
                            WHERE object_id=? AND object_type=?
                        """, (reps, s, d, hoje_str(), prox, lapses, card["id"], ItemType.FLASHCARD.value))
                        conn.commit()

                        st.toast(f"FSRS 🧠 | D:{d:.1f} | S:{s:.1f} | Retenção Atual:{r*100:.0f}% -> Próximo: {interval} dia(s)")
                        st.session_state["revelar_flashcard"] = False
                        st.rerun()

# ==============================================================================
# ANALYTICS
# ==============================================================================

with tab3:
    stats = get_tag_stats()
    st.subheader("Weak Areas & Mastery")

    if not stats:
        st.info("Sem dados. Resolva algumas questões primeiro!")
    else:
        rows = []
        for tag, s in stats.items():
            pct = (s["correct"] / s["total"]) * 100
            nivel_dominio = classify_tag(s["correct"], s["total"]).value
            
            rows.append({
                "Tag": tag,
                "Accuracy (%)": round(pct, 1),
                "Attempts": s["total"],
                "Mastery": nivel_dominio.upper()
            })

        df = pd.DataFrame(rows)
        df = df.sort_values("Accuracy (%)")

        st.dataframe(df, use_container_width=True)
        st.write("### Visão Gráfica (Taxa de Acerto %)")
        st.bar_chart(df.set_index("Tag")["Accuracy (%)"])

        criticos = df[df["Accuracy (%)"] < 50]
        if not criticos.empty:
            st.error("Critical weak concepts detected.")
            for _, row in criticos.iterrows():
                st.write(f"- {row['Tag']} ({row['Accuracy (%)']}%)")

# ==============================================================================
# HISTORY
# ==============================================================================

with tab4:
    st.header("Question History")
    questions = get_questions()

    if not questions:
        st.info("No questions answered yet.")
    else:
        filtro_sistema = st.selectbox("Filter by system", ["Todos"] + SISTEMAS_DISPONIVEIS)
        if filtro_sistema != "Todos":
            questions = [q for q in questions if q["sistema"] == filtro_sistema]

        st.write(f"Questions found: {len(questions)}")
        st.markdown("---")

        for q in questions:
            acertou = "✅" if q["answered_correctly"] else "❌"

            with st.expander(f"{acertou} | {q['sistema']} | {q['dificuldade']}"):
                st.caption(q["created_at"])
                
                st.markdown("### Tags")
                if q["tag_list"]:
                    st.write(" | ".join(q["tag_list"].split("|")))
                else:
                    st.write("Sem tags")

                st.markdown("---")
                try:
                    question_data = json.loads(q["question_json"])
                    st.markdown("### Vignette")
                    st.info(question_data["vignette"])

                    st.markdown("### Options")
                    for option in question_data["options"]:
                        if option.startswith(question_data["correct"]):
                            st.success(option)
                        else:
                            st.write(option)

                    st.markdown("---")
                    st.markdown("### Educational Objective")
                    st.warning(question_data["educational_objective"])
                except Exception as e:
                    st.error(f"Error loading question: {e}")