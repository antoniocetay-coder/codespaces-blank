from config import *
from fsrs import *
from sd import process_sd
from mastery import classify_tag_bkt, update_bkt
from analytics import *
from database import *
from ai_engine import *
from scheduler import *
from backup import *
from flashcard_engine import orquestrar_flashcards, gerar_flashcard_sob_demanda, gerar_mais_flashcards, gerar_flashcards_do_tutor
from ai_engine import explicar_duvida_tutor
from mastery import classify_tag_bkt, update_bkt
import streamlit as st
import json
import uuid
import pandas as pd
import datetime
import time

import plotly.express as px
import plotly.graph_objects as go

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
    "flashcards_rascunho": [],
    "flashcards_salvos": False,
    "checagem_feita": False,
    "resposta_tutor_atual": None  # <--- Salva a resposta do tutor na tela!
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

def sair_do_modo_estudo():
    for k in DEFAULTS.keys():
        del st.session_state[k]
    st.session_state["flashcards_rascunho"] = []
    st.session_state["flashcards_salvos"] = False
    st.session_state["checagem_feita"] = False
    st.session_state["resposta_tutor_atual"] = None
    st.rerun()

def proximo_item_fila():
    st.session_state["idx_atual"] += 1
    st.session_state["resposta_submetida"] = False
    st.session_state["letra_escolhida"] = None
    st.session_state["revelar_flashcard"] = False
    st.session_state["tempo_inicio_questao"] = None
    st.session_state["confianca_escolhida"] = None
    st.session_state["tempo_gasto"] = None
    st.session_state["resposta_tutor_atual"] = None
    
    st.session_state["flashcards_rascunho"] = []
    st.session_state["flashcards_salvos"] = False
    st.session_state["checagem_feita"] = False
    st.rerun()

def salvar_resultado_pendente(q_id, sistema, is_correct, tags, time_taken, confidence):
    marcar_questao_respondida(q_id, is_correct, time_taken, confidence)
    conn = get_conn()

    for tag in tags:
        # Puxa a probabilidade atual do banco
        row = conn.execute("SELECT correct, total, mastery_prob FROM tag_stats WHERE tag = ?", (tag,)).fetchone()
        
        if row:
            curr_prob = row["mastery_prob"] if row["mastery_prob"] is not None else 0.15
            corrects = row["correct"] + int(is_correct)
            totals = row["total"] + 1
        else:
            curr_prob = 0.15
            corrects = int(is_correct)
            totals = 1

        # Roda o motor Bayesiano
        new_prob = update_bkt(curr_prob, is_correct, confidence)

        # Salva o novo valor no banco
        conn.execute("""
            INSERT INTO tag_stats (tag, correct, total, mastery_prob) VALUES (?, ?, 1, ?)
            ON CONFLICT(tag) DO UPDATE SET 
                correct = ?, 
                total = ?, 
                mastery_prob = ?
        """, (tag, corrects, new_prob, corrects, totals, new_prob))

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
                
                is_learning = item_atual.get("is_learning", False)
                unlock_time = item_atual.get("unlock_time", 0)
                target_interval = item_atual.get("target_interval", 1)

                if unlock_time > time.time():
                    restante = int(unlock_time - time.time())
                    minutos = restante // 60
                    segundos = restante % 60
                    
                    is_last_unlocked = True
                    for next_item in fila[idx+1:]:
                        if next_item.get("unlock_time", 0) < time.time():
                            is_last_unlocked = False
                            break
                            
                    if is_last_unlocked:
                        st.warning("⏳ Aguardando tempo de fixação...")
                        st.info(f"O cérebro precisa de um intervalo. Este card estará disponível em **{minutos}m {segundos}s**.")
                        if st.button("🔄 Checar Tempo", use_container_width=True, type="primary"):
                            st.rerun()
                    else:
                        st.warning("⏳ Este card está em tempo de fixação (Spaced Learning).")
                        st.info("Pule para o próximo item e este card retornará automaticamente na hora certa.")
                        if st.button("Pular para o próximo disponível ➡️", use_container_width=True):
                            st.session_state["fila_estudo"].append(item_atual)
                            st.session_state["idx_atual"] += 1
                            st.rerun()
                            
                else:
                    st.markdown("## 🃏 Flashcard")
                    if is_learning:
                        st.caption("🔄 Fase de Fixação (Learning Step)")
                        
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

                        # ==========================================
                        # TUTOR AI E GERAÇÃO DE FLASHCARD DO TUTOR
                        # ==========================================
                        st.markdown("### 🧑‍🏫 Tutor AI")
                        col_tutor_input, col_tutor_btn = st.columns([4, 1])
                        
                        with col_tutor_input:
                            duvida_tutor = st.text_input(
                                "Dúvida", 
                                placeholder="Não entendeu o card? Peça uma explicação...", 
                                label_visibility="collapsed",
                                key=f"input_tutor_{card['id']}"
                            )
                            
                        with col_tutor_btn:
                            clicou_perguntar = st.button("🗣️ Perguntar", use_container_width=True, key=f"btn_tutor_{card['id']}")
                            
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
                            if st.button("⚡ Transformar Explicação em Flashcard", key=f"btn_transf_{card['id']}"):
                                with st.spinner("Forjando novo card..."):
                                    # Puxa o card atual (que está na tela) para passar como contexto
                                    cards_tela = [card] 
                                    rascunhos_tela = st.session_state.get("flashcards_rascunho", [])
                                    
                                    novos_cards = gerar_flashcards_do_tutor(
                                        st.session_state["resposta_tutor_atual"], 
                                        cards_tela, # A IA não vai poder repetir o card que você já tá vendo
                                        rascunhos_tela, 
                                        api_key
                                    )
                                    
                                    if novos_cards:
                                        st.session_state["flashcards_rascunho"].extend(novos_cards)
                                        st.rerun()
                        # Exibe os rascunhos caso o tutor tenha gerado algum card extra
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
                                    novo_front = st.text_area("Q (Front)", value=c_rascunho.get("front", ""), key=key_front)
                                    novo_back = st.text_area("A (Back)", value=c_rascunho.get("back", ""), key=key_back)
                                    editados.append({"front": novo_front, "back": novo_back, "tags": ["Tutor_Expansion"]})
                                
                                if st.form_submit_button("Aprovar e Salvar Todos"):
                                    for c in editados:
                                        # Salva usando o sistema original do card
                                        salvar_flashcard_db(c["front"], c["back"], card.get("sistema", "General"), c["tags"])
                                    st.session_state["flashcards_rascunho"] = [] # Esvazia após salvar
                                    st.success("✅ Card do Tutor Salvo!")
                                    time.sleep(1) # Dá um tempinho pra ver o aviso
                                    st.rerun()

                        st.markdown("---")

                        # ==========================================
                        # AVALIAÇÃO NORMAL (FSRS PURO)
                        # ==========================================
                        if not is_learning:
                            st.write("Avalie sua resposta (FSRS):")
                            g_info = {}
                            for g in [1, 2, 3, 4]:
                                g_info[g] = calcular_fsrs(g, card["difficulty"], card["stability"], max(0, elapsed_days), card["repetitions"], card["lapses"])
                            
                            col1, col2, col3, col4 = st.columns(4)
                            
                            if col1.button("Again (<1m)", use_container_width=True):
                                d, s, r, interval, reps, lapses = g_info[1]
                                conn = get_conn()
                                conn.execute("""
                                    INSERT INTO srs_state (object_id, object_type, repetitions, stability, difficulty, last_review, due, lapses)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(object_id, object_type) DO UPDATE SET repetitions=excluded.repetitions, stability=excluded.stability, difficulty=excluded.difficulty, last_review=excluded.last_review, due=excluded.due, lapses=excluded.lapses
                                """, (card["id"], ItemType.FLASHCARD.value, reps, s, d, hoje_str(), hoje_str(), lapses))
                                conn.commit()
                                
                                st.session_state["fila_estudo"].append({
                                    "type": "flashcard", "item": card, "is_learning": True,
                                    "unlock_time": time.time() + 60, "target_interval": interval
                                })
                                st.toast("Enviado para fixação (1 min) 🔄")
                                proximo_item_fila()

                            if col2.button("Hard (5m)", use_container_width=True):
                                d, s, r, interval, reps, lapses = g_info[2]
                                conn = get_conn()
                                conn.execute("""
                                    INSERT INTO srs_state (object_id, object_type, repetitions, stability, difficulty, last_review, due, lapses)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(object_id, object_type) DO UPDATE SET repetitions=excluded.repetitions, stability=excluded.stability, difficulty=excluded.difficulty, last_review=excluded.last_review, due=excluded.due, lapses=excluded.lapses
                                """, (card["id"], ItemType.FLASHCARD.value, reps, s, d, hoje_str(), hoje_str(), lapses))
                                conn.commit()
                                
                                st.session_state["fila_estudo"].append({
                                    "type": "flashcard", "item": card, "is_learning": True,
                                    "unlock_time": time.time() + 300, "target_interval": interval
                                })
                                st.toast("Enviado para fixação (5 min) 🔄")
                                proximo_item_fila()

                            if col3.button(f"Good ({g_info[3][3]}d)", use_container_width=True):
                                d, s, r, interval, reps, lapses = g_info[3]
                                prox = (now_utc() + datetime.timedelta(days=interval)).strftime("%Y-%m-%d")
                                conn = get_conn()
                                conn.execute("""
                                    INSERT INTO srs_state (object_id, object_type, repetitions, stability, difficulty, last_review, due, lapses)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(object_id, object_type) DO UPDATE SET repetitions=excluded.repetitions, stability=excluded.stability, difficulty=excluded.difficulty, last_review=excluded.last_review, due=excluded.due, lapses=excluded.lapses
                                """, (card["id"], ItemType.FLASHCARD.value, reps, s, d, hoje_str(), prox, lapses))
                                conn.commit()
                                st.toast(f"Próxima revisão em: {interval} dia(s)")
                                proximo_item_fila()

                            if col4.button(f"Easy ({g_info[4][3]}d)", use_container_width=True):
                                d, s, r, interval, reps, lapses = g_info[4]
                                prox = (now_utc() + datetime.timedelta(days=interval)).strftime("%Y-%m-%d")
                                conn = get_conn()
                                conn.execute("""
                                    INSERT INTO srs_state (object_id, object_type, repetitions, stability, difficulty, last_review, due, lapses)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(object_id, object_type) DO UPDATE SET repetitions=excluded.repetitions, stability=excluded.stability, difficulty=excluded.difficulty, last_review=excluded.last_review, due=excluded.due, lapses=excluded.lapses
                                """, (card["id"], ItemType.FLASHCARD.value, reps, s, d, hoje_str(), prox, lapses))
                                conn.commit()
                                st.toast(f"Próxima revisão em: {interval} dia(s)")
                                proximo_item_fila()
                        
                        else:
                            st.write("Avalie a sua fixação:")
                            col1, col2, col3 = st.columns(3)
                            
                            if col1.button("Again (<1m)", use_container_width=True):
                                item_atual["unlock_time"] = time.time() + 60
                                st.session_state["fila_estudo"].append(item_atual)
                                st.toast("Mantido na fixação (1 min) 🔄")
                                proximo_item_fila()
                                
                            if col2.button("Hard (5m)", use_container_width=True):
                                item_atual["unlock_time"] = time.time() + 300
                                st.session_state["fila_estudo"].append(item_atual)
                                st.toast("Mantido na fixação (5 min) 🔄")
                                proximo_item_fila()
                                
                            if col3.button(f"Good (Graduar)", use_container_width=True):
                                prox = (now_utc() + datetime.timedelta(days=target_interval)).strftime("%Y-%m-%d")
                                conn = get_conn()
                                conn.execute("UPDATE srs_state SET due=? WHERE object_id=? AND object_type=?", (prox, card["id"], ItemType.FLASHCARD.value))
                                conn.commit()
                                st.toast(f"Card Graduado! 🎉 Próximo em: {target_interval} dia(s)")
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
                    # PAINEL DE FORJA DE FLASHCARDS
                    # ==========================================
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
                                rascunhos_tela = st.session_state.get("flashcards_rascunho", [])
                                novos_cards = gerar_mais_flashcards(q, cards_banco_atual, rascunhos_tela, api_key)
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
                            label_visibility="collapsed"
                        )
                    with col_btn_especifico:
                        if st.button("🎯 Gerar Específico", use_container_width=True):
                            if pedido_customizado:
                                with st.spinner("Forjando card sob demanda..."):
                                    rascunhos_tela = st.session_state.get("flashcards_rascunho", [])
                                    novos_cards = gerar_flashcard_sob_demanda(q, pedido_customizado, cards_banco_atual, rascunhos_tela, api_key)
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
                        if len(rascunhos) > 0:
                            st.markdown("---")
                            chave_unica = f"form_{q_db['id']}" 
                            with st.form(key=chave_unica):
                                editados = []
                                for i, card in enumerate(rascunhos):
                                    st.write(f"**Card {i+1}**")
                                    key_front = f"f_{i}_{q_db['id']}"
                                    key_back = f"b_{i}_{q_db['id']}"
                                    novo_front = st.text_area("Q (Front)", value=card.get("front", ""), key=key_front)
                                    novo_back = st.text_area("A (Back)", value=card.get("back", ""), key=key_back)
                                    editados.append({"front": novo_front, "back": novo_back, "tags": card.get("tags", q["content_tags"])})
                                
                                if st.form_submit_button("Aprovar e Salvar Todos"):
                                    for c in editados:
                                        salvar_flashcard_db(c["front"], c["back"], q_db["sistema"], c["tags"])
                                    st.session_state["flashcards_salvos"] = True
                                    st.rerun()

                    st.markdown("---")
                    if st.button("Próximo Item ➡️", use_container_width=True, type="primary"):
                        proximo_item_fila()

# ==============================================================================
# TAB 2: TARGETED PRACTICE (Brute Force Mode)
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

# ==============================================================================
# TAB 3: ANALYTICS (Cockpit de Performance)
# ==============================================================================
with tab3:
    st.header("📊 Cockpit de Performance USMLE")
    
    sys_stats = get_system_stats()
    meta_stats = get_metacognition_stats()
    time_stats = get_time_stats()
    fsrs_data = get_fsrs_forecast()
    confusions = get_global_confusions()

    if not sys_stats:
        st.info("Ainda não há dados suficientes. Resolva algumas questões no QBank!")
    else:
        st.subheader("🕸️ Radar de Domínio por Sistema")
        
        df_sys = pd.DataFrame(sys_stats)
        df_sys["accuracy"] = (df_sys["acertos"] / df_sys["total"]) * 100
        
        fig_radar = px.line_polar(
            df_sys, r='accuracy', theta='sistema', line_close=True,
            range_r=[0, 100], markers=True, 
            color_discrete_sequence=['#00CC96']
        )
        fig_radar.update_traces(fill='toself')
        st.plotly_chart(fig_radar, use_container_width=True)

        st.markdown("---")

        col_meta, col_time = st.columns(2)

        with col_meta:
            st.subheader("🧠 Metacognição (Confiança vs Acerto)")
            if meta_stats:
                df_meta = pd.DataFrame(meta_stats)
                df_meta["Resultado"] = df_meta["answered_correctly"].apply(lambda x: "Acertou" if x == 1 else "Errou")
                
                fig_meta = px.bar(
                    df_meta, x="confidence_level", y="qtd", color="Resultado",
                    barmode="group",
                    color_discrete_map={"Acertou": "#28a745", "Errou": "#dc3545"},
                    labels={"confidence_level": "Nível de Confiança", "qtd": "Qtd Questões"}
                )
                st.plotly_chart(fig_meta, use_container_width=True)
            else:
                st.caption("Sem dados de confiança registrados ainda.")

        with col_time:
            st.subheader("⏱️ Arrasto Cognitivo (Tempo Médio)")
            if time_stats:
                df_time = pd.DataFrame(time_stats)
                df_time["Resultado"] = df_time["answered_correctly"].apply(lambda x: "Acertou" if x == 1 else "Errou")
                
                fig_time = px.bar(
                    df_time, x="avg_time", y="sistema", color="Resultado",
                    orientation='h', barmode='group',
                    color_discrete_map={"Acertou": "#28a745", "Errou": "#dc3545"},
                    labels={"avg_time": "Tempo Médio (s)", "sistema": "Sistema"}
                )
                fig_time.add_vline(x=90, line_width=2, line_dash="dash", line_color="red", annotation_text="USMLE Limit (90s)")
                st.plotly_chart(fig_time, use_container_width=True)
            else:
                st.caption("Sem dados de tempo registrados ainda.")

        st.markdown("---")
        
        col_fsrs, col_conf = st.columns(2)

        with col_fsrs:
            st.subheader("📅 Forecast de Revisões (FSRS)")
            if fsrs_data:
                df_fsrs = pd.DataFrame(fsrs_data)
                df_fsrs["due"] = pd.to_datetime(df_fsrs["due"])
                df_fsrs = df_fsrs[df_fsrs["due"].dt.date >= now_utc().date()]
                
                if not df_fsrs.empty:
                    df_fsrs["due_str"] = df_fsrs["due"].dt.strftime('%d/%m')
                    fig_fsrs = px.bar(
                        df_fsrs, x="due_str", y="qtd",
                        labels={"due_str": "Data", "qtd": "Flashcards Agendados"},
                        color_discrete_sequence=['#636EFA']
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
                    df_conf.rename(columns={"tag_correct": "O que era (Verdadeiro)", "tag_confused": "O que você achou (Falso)", "count": "Vezes que caiu"}),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.success("Você ainda não caiu em nenhum distrator de forma repetida!")
                
        # ==========================================
        # MICRO-TAGS (Com Teorema de Bayes - BKT)
        # ==========================================
        st.markdown("---")
        with st.expander("Ver Domínio BKT Completo por Micro-Tags"):
            conn = get_conn()
            rows_db = conn.execute("SELECT tag, correct, total, mastery_prob FROM tag_stats").fetchall()
            
            rows = []
            for r in rows_db:
                if r["total"] > 0:
                    prob = r["mastery_prob"] if r["mastery_prob"] is not None else (r["correct"]/r["total"])
                    pct_bkt = prob * 100
                    nivel_dominio = classify_tag_bkt(prob).value
                    
                    rows.append({
                        "Tag": r["tag"], 
                        "BKT Mastery (%)": round(pct_bkt, 1), 
                        "Attempts": r["total"], 
                        "Status": nivel_dominio.upper()
                    })

            if rows:
                df_tags = pd.DataFrame(rows).sort_values("BKT Mastery (%)")
                st.dataframe(df_tags, use_container_width=True, hide_index=True)

# ==============================================================================
# TAB 4: HISTORY
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