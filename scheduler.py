import random
import json
from datetime import datetime, timezone

from config import SISTEMAS_DISPONIVEIS
from database import (
    get_conn, get_tags_em_cooldown, get_pending_questions, 
    get_cards_hoje, salvar_questao, registrar_cooldown_tags
)
from analytics import get_tag_stats
from mastery import classify_tag
from ai_engine import TAXONOMIA_COMPLETA, gerar_questao

# ==============================================================================
# 1. SELEÇÃO ESTRATÉGICA DE TAGS (50-30-20)
# ==============================================================================
def selecionar_tags_estrategicas(sistemas_semana, qtd_tags=6):
    if not sistemas_semana:
        sistemas_semana = SISTEMAS_DISPONIVEIS

    todas_tags = set()
    for sistema in sistemas_semana:
        disciplinas = TAXONOMIA_COMPLETA.get(sistema, {})
        for tags_lista in disciplinas.values():
            if isinstance(tags_lista, list):
                todas_tags.update(tags_lista)

    # Cooldown de 48 horas
    tags_bloqueadas = get_tags_em_cooldown(horas=48)
    tags_disponiveis = [t for t in todas_tags if t not in tags_bloqueadas]

    # Prevenção: Se estudou demais e esgotou tudo, fura a bolha
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

    escolhidas = []
    # Mix de Ouro: 3 Fraquezas, 2 Novos, 1 Domínio
    escolhidas.extend(sortear_e_remover(categorias["LEARNING"], 3))
    escolhidas.extend(sortear_e_remover(categorias["NEW"], 2))
    escolhidas.extend(sortear_e_remover(categorias["CONSOLIDATED"], 1))

    # Preenche o buraco se faltar tag
    faltam = qtd_tags - len(escolhidas)
    if faltam > 0:
        pool_reserva = categorias["LEARNING"] + categorias["NEW"] + categorias["CONSOLIDATED"]
        escolhidas.extend(sortear_e_remover(pool_reserva, faltam))

    return escolhidas

# ==============================================================================
# 2. ORQUESTRAÇÃO DE FILA (COGNITIVE CHUNKING)
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
            # Aquecimento e Descompressão: 3 Cards
            for _ in range(3):
                if idx_c < len(cards_hoje):
                    fila.append({"type": "flashcard", "item": cards_hoje[idx_c]})
                    idx_c += 1
            # Deep Work Clínico: 2 Vignettes
            for _ in range(2):
                if idx_q < len(questoes_pendentes):
                    fila.append({"type": "question", "item": questoes_pendentes[idx_q]})
                    idx_q += 1

    return fila

# ==============================================================================
# 3. GERAÇÃO EM BATCH (BACKGROUND)
# ==============================================================================
def gerar_lote_background(sistemas_semana, dificuldade, api_key, qtd_questoes=3):
    """Gera 'N' questões de uma vez, focadas estrategicamente, salvando como 'pending'."""
    sucessos = 0
    if not sistemas_semana:
        sistemas_semana = SISTEMAS_DISPONIVEIS
        
    for _ in range(qtd_questoes):
        sistema = random.choice(sistemas_semana)
        tags_alvo = selecionar_tags_estrategicas([sistema], qtd_tags=6)
        
        # Chama a IA passando as tags exatas que o Scheduler calculou
        q = gerar_questao(sistema, dificuldade, api_key, tags_alvo=tags_alvo)
        
        if q:
            # Salva no banco de forma invisível
            from database import salvar_questao, registrar_cooldown_tags
            salvar_questao(sistema, dificuldade, q, acertou=False, tags=q["content_tags"], status="pending")
            # Envia as tags para a geladeira de 48h
            registrar_cooldown_tags(q["content_tags"])
            sucessos += 1
            
    return sucessos