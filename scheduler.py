import random
import sqlite3
from datetime import datetime, timezone

from config import SISTEMAS_DISPONIVEIS
from db.core import get_conn
from db.questions import get_pending_questions, salvar_questao
from db.flashcards import get_cards_hoje
from db.confusions import get_tags_em_cooldown, registrar_cooldown_tags
from analytics import get_tag_stats, get_system_stats
from mastery import classify_tag
from taxonomy import TAXONOMIA_COMPLETA
from prerequisites import interceptar_com_prerequisitos

# ==============================================================================
# 1. SELEÇÃO ESTRATÉGICA DE TAGS (Com BKT e Grafo)
# ==============================================================================
def selecionar_tags_estrategicas(sistemas_semana, qtd_tags=6):
    conn = get_conn()
    
    # 1. Pega as tags como já fazia antes
    if not sistemas_semana:
        sistemas_semana = SISTEMAS_DISPONIVEIS

    todas_tags = set()
    for sistema in sistemas_semana:
        disciplinas = TAXONOMIA_COMPLETA.get(sistema, {})
        for tags_lista in disciplinas.values():
            if isinstance(tags_lista, list):
                todas_tags.update(tags_lista)

    tags_bloqueadas = get_tags_em_cooldown(horas=48)
    tags_disponiveis = [t for t in todas_tags if t not in tags_bloqueadas]

    if not tags_disponiveis:
        tags_disponiveis = list(todas_tags)

    stats = get_tag_stats()
    categorias = {"LEARNING": [], "NEW": [], "CONSOLIDATED": []}

    for tag in tags_disponiveis:
        s = stats.get(tag, {"correct": 0, "total": 0})
        nivel = classify_tag(s["correct"], s["total"]).name

        if nivel == "LEARNING":
            categorias["LEARNING"].append(tag)
        elif nivel in ["DRONE", "NEW"]:
            categorias["NEW"].append(tag)
        else:
            categorias["CONSOLIDATED"].append(tag)

    def sortear_e_remover(lista, qtd):
        sorteio = random.sample(lista, min(qtd, len(lista)))
        for item in sorteio:
            lista.remove(item)
        return sorteio

    # 2. Sorteia as tags raízes (Onde o aluno é fraco)
    escolhidas_raiz = []
    escolhidas_raiz.extend(sortear_e_remover(categorias["LEARNING"], 3))
    
    # =====================================================================
    # 🌟 A MÁGICA DA ONTOLOGIA ACONTECE AQUI 🌟
    # Para cada tag que o aluno é fraco, buscamos no Grafo o que CAUSA ela
    # ou os SINTOMAS (MANIFESTS_AS) para forçar raciocínio de 2ª ordem.
    # =====================================================================
    tags_segunda_ordem = set()
    for tag_fraca in escolhidas_raiz:
        try:
            rows = conn.execute("""
                SELECT source, target, relation FROM ontology_edges 
                WHERE source = ? OR target = ?
                ORDER BY RANDOM() LIMIT 2
            """, (tag_fraca, tag_fraca)).fetchall()
            
            for r in rows:
                if r['source'] != tag_fraca and r['source'] not in tags_bloqueadas:
                    tags_segunda_ordem.add(r['source'])
                if r['target'] != tag_fraca and r['target'] not in tags_bloqueadas:
                    tags_segunda_ordem.add(r['target'])
        except sqlite3.OperationalError:
            pass # Caso a tabela ontology_edges ainda não exista

    escolhidas = escolhidas_raiz + list(tags_segunda_ordem)

    # Completa o resto do lote com NEW e CONSOLIDATED
    faltam = qtd_tags - len(escolhidas)
    if faltam > 0:
        escolhidas.extend(sortear_e_remover(categorias["NEW"], min(2, faltam)))
        
    faltam = qtd_tags - len(escolhidas)
    if faltam > 0:
        pool_reserva = categorias["LEARNING"] + categorias["NEW"] + categorias["CONSOLIDATED"]
        escolhidas.extend(sortear_e_remover(pool_reserva, faltam))

    return escolhidas[:qtd_tags]
# ==============================================================================
# 2. ORQUESTRAÇÃO DE FILA
# ==============================================================================
def montar_fila_estudo(modo_escolhido):
    cards_hoje = get_cards_hoje()
    questoes_pendentes = get_pending_questions()

    fila = []

    if modo_escolhido == "Review":
        for c in cards_hoje:
            fila.append({"type": "flashcard", "item": c})

    elif modo_escolhido == "QBank":
        for q in questoes_pendentes:
            fila.append({"type": "question", "item": q})

    elif modo_escolhido == "Interleaved":
        idx_c = 0
        idx_q = 0
        while idx_c < len(cards_hoje) or idx_q < len(questoes_pendentes):
            for _ in range(3):
                if idx_c < len(cards_hoje):
                    fila.append({"type": "flashcard", "item": cards_hoje[idx_c]})
                    idx_c += 1
            for _ in range(2):
                if idx_q < len(questoes_pendentes):
                    fila.append({"type": "question", "item": questoes_pendentes[idx_q]})
                    idx_q += 1

    return fila

# ==============================================================================
# 3. GERAÇÃO EM BATCH (OTIMIZADO)
# ==============================================================================
# No final do scheduler.py, substitua a função gerar_lote_background:

def gerar_lote_background(sistemas_semana, dificuldade, api_key, qtd_questoes=3):
    sucessos = 0
    if not sistemas_semana:
        sistemas_semana = SISTEMAS_DISPONIVEIS
        
    MAX_POR_CALL = 5
    chunks = []
    restante = qtd_questoes
    
    while restante > 0:
        if restante >= MAX_POR_CALL:
            chunks.append(MAX_POR_CALL)
            restante -= MAX_POR_CALL
        else:
            chunks.append(restante)
            restante = 0

    from ai_engine import gerar_lote_questoes

    for chunk_size in chunks:
        sistema = random.choice(sistemas_semana)
        tags_alvo = selecionar_tags_estrategicas([sistema], qtd_tags=chunk_size)
        
        # ==========================================
        # NOVIDADE: CALCULA O COGNITIVE LEVEL
        # ==========================================
        stats = get_tag_stats()
        bkt_sum = 0
        for t in tags_alvo:
            s = stats.get(t, {})
            prob = s.get("mastery_prob", 0.15) if s.get("mastery_prob") is not None else 0.15
            bkt_sum += prob
            
        media_bkt = bkt_sum / len(tags_alvo) if tags_alvo else 0.15
        
        if media_bkt < 0.50:
            cognitive_order = "1st Order (Diagnosis/Presentation)"
        elif media_bkt < 0.80:
            cognitive_order = "2nd Order (Pathophysiology/Next Step in Management)"
        else:
            cognitive_order = "3rd Order (Pharmacology Mechanism/Embryology/Genetic Defect)"
            
        # Faz a chamada enviando o Nível Cognitivo!
        questoes_geradas = gerar_lote_questoes(sistema, dificuldade, cognitive_order, api_key, tags_alvo, chunk_size)
        
        for q in questoes_geradas:
            salvar_questao(sistema, dificuldade, q, acertou=False, tags=q["content_tags"], status="pending")
            registrar_cooldown_tags(q["content_tags"])
            sucessos += 1
            
    return sucessos

# ==============================================================================
# 4. PLANNER PEDAGÓGICO
# ==============================================================================
def gerar_planos_estudo():
    rows = get_system_stats()
    if not rows:
        return [
            {"titulo": "Combo 1", "sistemas": random.sample(SISTEMAS_DISPONIVEIS, 2)},
            {"titulo": "Combo 2", "sistemas": random.sample(SISTEMAS_DISPONIVEIS, 2)},
            {"titulo": "Combo 3", "sistemas": random.sample(SISTEMAS_DISPONIVEIS, 2)}
        ]

    stats = {r["sistema"]: (r["acertos"] / r["total"]) for r in rows if r["total"] > 0}
    unseen = [s for s in SISTEMAS_DISPONIVEIS if s not in stats]
    critical = sorted([s for s in stats if stats[s] < 0.50], key=lambda x: stats[x])
    developing = sorted([s for s in stats if 0.50 <= stats[s] < 0.75], key=lambda x: stats[x])
    mastered = sorted([s for s in stats if stats[s] >= 0.75], key=lambda x: stats[x])
    
    planos = []

    sistemas_c1 = critical[:2] if len(critical) >= 2 else (critical + developing)[:2]
    if not sistemas_c1: sistemas_c1 = random.sample(SISTEMAS_DISPONIVEIS, 2)
    planos.append({"titulo": "🚨 Foco Crítico", "sistemas": sistemas_c1})

    sistemas_c2 = []
    if developing: sistemas_c2.append(developing[-1])
    if unseen: sistemas_c2.append(unseen[0])
    if len(sistemas_c2) < 2: sistemas_c2 = random.sample(SISTEMAS_DISPONIVEIS, 2)
    planos.append({"titulo": "🏗️ Construção", "sistemas": sistemas_c2})

    sistemas_c3 = unseen[:2] if len(unseen) >= 2 else (unseen + mastered)[:2]
    if len(sistemas_c3) < 2: sistemas_c3 = random.sample(SISTEMAS_DISPONIVEIS, 2)
    planos.append({"titulo": "🧭 Expansão", "sistemas": sistemas_c3})

    return planos