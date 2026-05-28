from config import *
from fsrs import *
from sd import process_sd
from mastery import classify_tag
from analytics import *
from database import *
from ai_engine import *
from scheduler import *
from backup import *
from flashcard_engine import orquestrar_flashcards, gerar_flashcard_sob_demanda, gerar_mais_flashcards

import streamlit as st
import json
import uuid
import pandas as pd
import datetime
import time

# ==============================================================================
# DATABASE & STARTUP
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
    "flashcards_rascunho": [],  # <--- Adicionado explicitamente aqui
    "flashcards_salvos": False
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

def sair_do_modo_estudo():
    for k in DEFAULTS.keys():
        del st.session_state[k]
    # Limpa os rascunhos à força ao sair
    st.session_state["flashcards_rascunho"] = []
    st.session_state["flashcards_salvos"] = False
    st.session_state["checagem_feita"] = False
    st.rerun()

def proximo_item_fila():
    st.session_state["idx_atual"] += 1
    st.session_state["resposta_submetida"] = False
    st.session_state["letra_escolhida"] = None
    st.session_state["revelar_flashcard"] = False
    st.session_state["tempo_inicio_questao"] = None
    st.session_state["confianca_escolhida"] = None
    st.session_state["tempo_gasto"] = None
    
    # EM VEZ DE DELETAR, NÓS ESVAZIAMOS AS LISTAS E VARIÁVEIS À FORÇA
    st.session_state["flashcards_rascunho"] = []
    st.session_state["flashcards_salvos"] = False
    st.session_state["checagem_feita"] = False
    
    st.rerun()
    
    if "flashcards_rascunho" in st.session_state:
        del st.session_state["flashcards_rascunho"]
    if "flashcards_salvos" in st.session_state:
        del st.session_state["flashcards_salvos"]
    if "checagem_feita" in st.session_state:
        del st.session_state["checagem_feita"]
    st.rerun()

def salvar_resultado_pendente(q_id, sistema, is_correct, tags, time_taken, confidence):
    marcar_questao_respondida(q_id, is_correct, time_taken, confidence)
    conn = get_conn()

    for tag in tags:
        conn.execute("""
            INSERT INTO tag_stats (tag, correct, total) VALUES (?, ?, 1)
            ON CONFLICT(tag) DO UPDATE SET correct = correct + excluded.correct, total = total + 1
        """, (tag, int(is_correct)))

    if not is_correct:
        conn.execute("UPDATE erros_por_sistema SET total = total + 1 WHERE sistema = ?", (sistema,))

    conn.commit()

# ==============================================================================
# UI - SIDEBAR
# ==============================================================================
with st.sidebar:
    st.header("Configurações")
    try:
        chave_salva = st.secrets.get("GEMINI_API_KEY", "")
    except:
        chave_salva = ""
    api_key = st.text_input("Gemini API Key", value=chave_salva, type="password")
    dificuldade = st.selectbox("Difficulty", ["Easy", "Medium", "Hard", "Insane"])

st.title("USMLE ECO-SYSTEM V2")

tab1, tab2, tab3, tab4 = st.tabs(["🏠 Dashboard", "🎯 Targeted Practice", "📊 Analytics", "📜 History"])

# ==============================================================================
# TAB 1: DASHBOARD E MODO DE ESTUDO
# ==============================================================================
with tab1:
    if st.session_state["modo_estudo"] is None:
        cards_hoje = get_cards_hoje()
        questoes_pendentes = get_pending_questions()
        
        col1, col2 = st.columns(2)
        col1.metric("🃏 Flashcards Vencidos", len(cards_hoje))
        col2.metric("📝 Questões na Fila", len(questoes_pendentes))
        
        st.markdown("---")
        st.subheader("1. Planejamento Semanal & Preparação")
        
        qtd_gerar = st.slider("Quantas questões deseja gerar neste lote?", min_value=1, max_value=10, value=3)
        
        from scheduler import gerar_planos_estudo
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
                    
                    if st.button(f"Gerar Plano {i+1}", use_container_width=True, key=f"btn_plano_{i}"):
                        gerando_agora = True
                        if not api_key:
                            st.error("API Key necessária.")
                        else:
                            with st.spinner(f"Gerando {qtd_gerar} questões para {', '.join(plano['sistemas'])}..."):
                                sucessos = gerar_lote_background(plano['sistemas'], dificuldade, api_key, qtd_questoes=qtd_gerar)
                                st.success(f"{sucessos} Questões geradas!")
                                st.rerun()

        st.markdown("---")
        st.subheader("2. Escolha seu Modo de Estudo de Hoje")
        
        c1, c2, c3 = st.columns(3)
        
        with c1:
            if st.button("🔋 Review Mode\n(Apenas Anki)", use_container_width=True, disabled=gerando_agora):
                st.session_state["modo_estudo"] = "Review"
                st.session_state["fila_estudo"] = montar_fila_estudo("Review")
                st.rerun()
        with c2:
            if st.button("⚡ QBank Mode\n(Apenas Questões)", use_container_width=True, disabled=gerando_agora):
                st.session_state["modo_estudo"] = "QBank"
                st.session_state["fila_estudo"] = montar_fila_estudo("QBank")
                st.rerun()
        with c3:
            if st.button("🧠 Interleaved Mode\n(O Super Deck)", use_container_width=True, disabled=gerando_agora):
                st.session_state["modo_estudo"] = "Interleaved"
                st.session_state["fila_estudo"] = montar_fila_estudo("Interleaved")
                st.rerun()

    else:
        fila = st.session_state["fila_estudo"]
        idx = st.session_state["idx_atual"]
        
        st.button("🔙 Sair e Voltar ao Dashboard", on_click=sair_do_modo_estudo)
        
        if idx >= len(fila):
            st.success("🎉 Sessão Concluída! Você destruiu a fila de hoje.")
            st.balloons()
        else:
            item_atual = fila[idx]
            progresso = f"Progresso: {idx + 1} / {len(fila)}"
            st.progress((idx) / len(fila), text=progresso)
            
            # ==========================================
            # RENDERIZAR FLASHCARD
            # ==========================================
            if item_atual["type"] == "flashcard":
                card = item_atual["item"]
                st.markdown("## 🃏 Flashcard")
                st.info(card["front"])

                if not st.session_state["revelar_flashcard"]:
                    if st.button("Mostrar Resposta", use_container_width=True):
                        st.session_state["revelar_flashcard"] = True
                        st.rerun()
                else:
                    st.success(card["back"])
                    hoje_data = now_utc().date()
                    try:
                        last_rev_data = datetime.datetime.strptime(card["last_review"], "%Y-%m-%d").date()
                        elapsed_days = (hoje_data - last_rev_data).days
                    except:
                        elapsed_days = 0

                    st.markdown("### 🧠 Saúde da Memória")
                    estado_memoria = process_sd(card["stability"], card["difficulty"], max(0, elapsed_days))
                    st.json(estado_memoria)
                    st.markdown("---")

                    st.write("Avalie sua resposta (FSRS):")
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
                                    INSERT INTO srs_state (object_id, object_type, repetitions, stability, difficulty, last_review, due, lapses)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(object_id, object_type) 
                                    DO UPDATE SET repetitions=excluded.repetitions, stability=excluded.stability, 
                                    difficulty=excluded.difficulty, last_review=excluded.last_review, due=excluded.due, lapses=excluded.lapses
                                """, (card["id"], ItemType.FLASHCARD.value, reps, s, d, hoje_str(), prox, lapses))
                                conn.commit()

                                st.toast(f"D:{d:.1f} | S:{s:.1f} -> Próximo em: {interval} dia(s)")
                                proximo_item_fila()

            # ==========================================
            # RENDERIZAR QUESTÃO (QBANK)
            # ==========================================
            elif item_atual["type"] == "question":
                q_db = item_atual["item"]
                q = json.loads(q_db["question_json"])
                
                if st.session_state["tempo_inicio_questao"] is None:
                    st.session_state["tempo_inicio_questao"] = time.time()

                st.markdown(f"## 📝 Questão de {q_db['sistema']} ({q_db['dificuldade']})")
                st.info(q["vignette"])

                escolha = st.radio("Escolha a melhor alternativa:", q["options"], index=None, disabled=st.session_state["resposta_submetida"])
                
                st.write("**Qual seu nível de confiança nesta resposta?**")
                confianca = st.radio(
                    "Confiança", 
                    ["Certeza Absoluta", "Dúvida entre 2", "Chute Cego"], 
                    horizontal=True, 
                    index=None,
                    label_visibility="collapsed",
                    disabled=st.session_state["resposta_submetida"]
                )

                if not st.session_state["resposta_submetida"]:
                    if st.button("Submeter", disabled=(escolha is None or confianca is None)):
                        tempo_gasto = int(time.time() - st.session_state["tempo_inicio_questao"])
                        letra = escolha[0].upper()
                        correto = (letra == q["correct"])

                        st.session_state["resposta_submetida"] = True
                        st.session_state["acertou_ultima"] = correto
                        st.session_state["letra_escolhida"] = letra
                        st.session_state["confianca_escolhida"] = confianca
                        st.session_state["tempo_gasto"] = tempo_gasto

                        salvar_resultado_pendente(q_db["id"], q_db["sistema"], correto, q["content_tags"], tempo_gasto, confianca)

                        if not correto and confianca != "Chute Cego":
                            dist_tags = q.get("distractor_tags", {})
                            tag_correta = dist_tags.get(q["correct"])
                            tag_errada = dist_tags.get(letra)
                            if tag_correta and tag_errada:
                                registrar_confusao(tag_correta, tag_errada)

                        st.rerun()
                
                if st.session_state["resposta_submetida"]:
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

                    # ==========================================
                    # PAINEL DE FORJA DE FLASHCARDS (100% Manual)
                    # ==========================================
                    st.markdown("---")
                    st.markdown("### 🛠️ Forja de Flashcards")
                    
                    # Linha 1: Botões de Geração Rápida
                    col_btn_erro, col_btn_mais = st.columns(2)
                    with col_btn_erro:
                        if st.button("💡 Analisar meu Erro/Chute", use_container_width=True):
                            with st.spinner("Analisando seu viés cognitivo..."):
                                cards_ia = orquestrar_flashcards(
                                    q, 
                                    st.session_state["letra_escolhida"], 
                                    st.session_state["acertou_ultima"],
                                    st.session_state["confianca_escolhida"],
                                    api_key
                                )
                                if cards_ia:
                                    if "flashcards_rascunho" not in st.session_state:
                                        st.session_state["flashcards_rascunho"] = []
                                    st.session_state["flashcards_rascunho"].extend(cards_ia)
                                    st.rerun()

                    with col_btn_mais:
                        if st.button("➕ Explorar Outros Ângulos", use_container_width=True):
                            with st.spinner("Buscando novos ângulos da doença..."):
                                atuais = st.session_state.get("flashcards_rascunho", [])
                                novos_cards = gerar_mais_flashcards(q, atuais, api_key)
                                if novos_cards:
                                    if "flashcards_rascunho" not in st.session_state:
                                        st.session_state["flashcards_rascunho"] = []
                                    st.session_state["flashcards_rascunho"].extend(novos_cards)
                                    st.rerun()

                    # Linha 2: Geração Sob Demanda
                    st.write("") # Espaçamento
                    col_input, col_btn_especifico = st.columns([3, 1])
                    with col_input:
                        pedido_customizado = st.text_input(
                            "Lacuna Específica", 
                            placeholder="Ex: Fisiopatologia da alternativa C", 
                            label_visibility="collapsed"
                        )
                    with col_btn_especifico:
                        if st.button("🎯 Gerar Específico", use_container_width=True):
                            if pedido_customizado:
                                with st.spinner("Forjando card sob demanda..."):
                                    novos_cards = gerar_flashcard_sob_demanda(q, pedido_customizado, api_key)
                                    if novos_cards:
                                        if "flashcards_rascunho" not in st.session_state:
                                            st.session_state["flashcards_rascunho"] = []
                                        st.session_state["flashcards_rascunho"].extend(novos_cards)
                                        st.rerun()
                            else:
                                st.warning("Digite algo ao lado.")

                    # ==========================================
                    # EXIBIÇÃO E APROVAÇÃO DOS RASCUNHOS
                    # ==========================================
                    if st.session_state.get("flashcards_salvos", False):
                        st.success("✅ Cards salvos no Baralho!")
                    else:
                        rascunhos = st.session_state.get("flashcards_rascunho", [])
                        
                        # NOVA REGRA: Só desenha se a lista REALMENTE tiver algo novo
                        if len(rascunhos) > 0:
                            st.markdown("---")
                            
                            # Amarramos a chave do Form ao ID exato desta questão
                            chave_unica = f"form_{q_db['id']}" 
                            
                            with st.form(key=chave_unica):
                                editados = []
                                for i, card in enumerate(rascunhos):
                                    st.write(f"**Card {i+1}**")
                                    # As chaves text_area agora também são exclusivas dessa questão!
                                    key_front = f"f_{i}_{q_db['id']}"
                                    key_back = f"b_{i}_{q_db['id']}"
                                    
                                    novo_front = st.text_area("Q (Front)", value=card.get("front", ""), key=key_front)
                                    novo_back = st.text_area("A (Back)", value=card.get("back", ""), key=key_back)
                                    
                                    editados.append({
                                        "front": novo_front, 
                                        "back": novo_back, 
                                        "tags": card.get("tags", q["content_tags"])
                                    })
                                
                                if st.form_submit_button("Aprovar e Salvar Todos"):
                                    for c in editados:
                                        salvar_flashcard_db(c["front"], c["back"], q_db["sistema"], c["tags"])
                                    st.session_state["flashcards_salvos"] = True
                                    st.rerun()

                    st.markdown("---")
                    if st.button("Próximo Item ➡️", use_container_width=True, type="primary"):
                        proximo_item_fila()

# ==============================================================================
# TAB 2, 3 E 4
# ==============================================================================
with tab2:
    st.header("🎯 Prática Focada (Brute Force)")
    st.write("Véspera de prova? Escolha uma tag específica e force a geração ignorando o Cooldown.")
    
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
                q_brute = gerar_questao(sys_brute, dificuldade, api_key, tags_alvo=[tag_alvo])
                if q_brute:
                    salvar_questao(sys_brute, dificuldade, q_brute, False, q_brute["content_tags"], status="answered")
                    st.success("Questão gerada e salva no seu Histórico!")
                    with st.expander("Ver Questão Gerada", expanded=True):
                        st.info(q_brute["vignette"])
                        for opt in q_brute["options"]:
                            st.write(opt)
                        st.success(f"Correta: {q_brute['correct']}")

with tab3:
    stats = get_tag_stats()
    st.subheader("Weak Areas & Mastery")

    if not stats:
        st.info("Sem dados. Resolva algumas questões primeiro!")
    else:
        rows = []
        for tag, s in stats.items():
            if s["total"] > 0:
                pct = (s["correct"] / s["total"]) * 100
                nivel_dominio = classify_tag(s["correct"], s["total"]).value
                rows.append({"Tag": tag, "Accuracy (%)": round(pct, 1), "Attempts": s["total"], "Mastery": nivel_dominio.upper()})

        if rows:
            df = pd.DataFrame(rows).sort_values("Accuracy (%)")
            st.dataframe(df, use_container_width=True)
            st.bar_chart(df.set_index("Tag")["Accuracy (%)"])

            criticos = df[df["Accuracy (%)"] < 50]
            if not criticos.empty:
                st.error("Critical weak concepts detected.")
                for _, row in criticos.iterrows():
                    st.write(f"- {row['Tag']} ({row['Accuracy (%)']}%)")

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
        for q in questions:
            acertou = "✅" if q["answered_correctly"] else "❌"
            with st.expander(f"{acertou} | {q['sistema']} | {q['dificuldade']}"):
                st.caption(q["created_at"])
                st.write(" | ".join(q["tag_list"].split("|"))) if q.get("tag_list") else st.write("Sem tags")
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
                except Exception as e:
                    st.error("Error loading question.")