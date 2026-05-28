import random
import json
from datetime import datetime, timezone

from config import SISTEMAS_DISPONIVEIS
from database import (
    get_conn, get_tags_em_cooldown, get_pending_questions, 
    get_cards_hoje, salvar_questao, registrar_cooldown_tags,
    get_system_stats  # <-- Adicionado aqui!
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

# ==============================================================================
# 4. PLANNER PEDAGÓGICO (ZONA DE DESENVOLVIMENTO PROXIMAL)
# ==============================================================================
def sugerir_sistemas(limit=3):
    """
    Usa regras de Carga Cognitiva para orquestrar a sessão perfeita.
    """
    rows = get_system_stats()

    if not rows:
        # Se for o primeiro dia de uso absoluto do app
        return [(s, "Avaliação Diagnóstica (Inédito)") for s in random.sample(SISTEMAS_DISPONIVEIS, limit)]

    stats = {r["sistema"]: (r["acertos"] / r["total"]) for r in rows if r["total"] > 0}
    
    total_acertos = sum(r["acertos"] for r in rows)
    total_questoes = sum(r["total"] for r in rows)
    acuracia_global = total_acertos / total_questoes if total_questoes > 0 else 0

    # Categorização
    unseen = [s for s in SISTEMAS_DISPONIVEIS if s not in stats]
    critical = [s for s, pct in stats.items() if pct < 0.50]
    developing = [s for s, pct in stats.items() if 0.50 <= pct < 0.75]
    mastered = [s for s, pct in stats.items() if pct >= 0.75]

    critical.sort(key=lambda x: stats[x])
    developing.sort(key=lambda x: stats[x])
    mastered.sort(key=lambda x: stats[x])

    recomendações = []

    # SLOT 1: A HEMORRAGIA
    if critical:
        sys = critical.pop(0)
        recomendações.append((sys, f"Intervenção Aguda ({stats[sys]*100:.0f}%) - Foco em tapar lacunas de base."))
    elif developing:
        sys = developing.pop(0)
        recomendações.append((sys, f"Consolidação ({stats[sys]*100:.0f}%) - Foco em refinar o diagnóstico diferencial."))

    # SLOT 2: A CONSTRUÇÃO
    if developing:
        sys = developing.pop(0)
        recomendações.append((sys, f"Aprimoramento Clínico ({stats[sys]*100:.0f}%) - Foco em armadilhas de distratores."))
    elif critical:
        sys = critical.pop(0)
        recomendações.append((sys, f"Remediação Secundária ({stats[sys]*100:.0f}%) - Necessita revisão de conceitos vitais."))
    elif mastered:
        sys = mastered.pop(0)
        recomendações.append((sys, f"Manutenção de Domínio ({stats[sys]*100:.0f}%) - Prevenção de esquecimento (FSRS)."))

    # SLOT 3: NOVO vs REVISÃO
    if acuracia_global > 0.60 and unseen:
        sys = unseen.pop(0)
        recomendações.append((sys, "Expansão de Fronteira (Inédito) - Base sólida permite aprender novos sistemas."))
    else:
        if developing:
            sys = developing.pop(0)
            recomendações.append((sys, f"Reforço de Base ({stats[sys]*100:.0f}%) - Sobrecarga evitada. Matéria nova suspensa."))
        elif mastered:
            sys = mastered.pop(0)
            recomendações.append((sys, f"Reativação Passiva ({stats[sys]*100:.0f}%) - Aumentar confiança e fixar matéria antiga."))

    return recomendações[:limit]
from database import get_system_stats
import random
from config import SISTEMAS_DISPONIVEIS

from database import get_system_stats
import random
from config import SISTEMAS_DISPONIVEIS

from database import get_system_stats
import random
from config import SISTEMAS_DISPONIVEIS

def gerar_planos_estudo():
    """Gera 3 planos (combos de sistemas) para a tela inicial."""
    rows = get_system_stats()
    
    # Se o app for novo e não tiver dados, sugere combos aleatórios
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

    # CAIXA 1: Os piores sistemas (Hemorragia)
    sistemas_c1 = critical[:2] if len(critical) >= 2 else (critical + developing)[:2]
    if not sistemas_c1: sistemas_c1 = random.sample(SISTEMAS_DISPONIVEIS, 2)
    planos.append({"titulo": "🚨 Foco Crítico", "sistemas": sistemas_c1})

    # CAIXA 2: Sistemas medianos + Inéditos
    sistemas_c2 = []
    if developing: sistemas_c2.append(developing[-1])
    if unseen: sistemas_c2.append(unseen[0])
    if len(sistemas_c2) < 2: sistemas_c2 = random.sample(SISTEMAS_DISPONIVEIS, 2)
    planos.append({"titulo": "🏗️ Construção", "sistemas": sistemas_c2})

    # CAIXA 3: Inéditos + Domínio
    sistemas_c3 = unseen[:2] if len(unseen) >= 2 else (unseen + mastered)[:2]
    if len(sistemas_c3) < 2: sistemas_c3 = random.sample(SISTEMAS_DISPONIVEIS, 2)
    planos.append({"titulo": "🧭 Expansão", "sistemas": sistemas_c3})

    return planos