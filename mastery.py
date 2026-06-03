from enum import Enum

class MasteryLevel(Enum):
    DRONE        = "drone"         # Nunca tocado
    NEW          = "new"           # Probabilidade < 30%
    LEARNING     = "learning"      # Probabilidade 30% - 65%
    CONSOLIDATED = "consolidated"  # Probabilidade 65% - 90%
    MASTERED     = "mastered"      # Probabilidade > 90%

# Parâmetros base do modelo BKT para o USMLE
P_L0 = 0.15  # O aluno tem 15% de chance de já saber o assunto da faculdade
P_T  = 0.10  # A cada questão, tem 10% de chance de "aprender/transicionar" o assunto

def update_bkt(current_prob, is_correct, confidence=None):
    """
    Atualiza a probabilidade de domínio da tag usando o Teorema de Bayes,
    ajustando os pesos baseado na metacognição do aluno.
    """
    if current_prob is None:
        current_prob = P_L0

    # Ajuste Dinâmico de P(G) - Guess (Chute) e P(S) - Slip (Deslize)
    if confidence == "Chute Cego":
        p_guess = 0.80  # Se chutou e acertou, a probabilidade de ter sido sorte é enorme
        p_slip = 0.10
    elif confidence == "Certeza Absoluta":
        p_guess = 0.05
        p_slip = 0.05   # Se errou tendo certeza, não foi deslize, é uma lacuna real grave
    else:
        p_guess = 0.20  # USMLE tem 5 alternativas (1/5 = 20% de chance natural)
        p_slip = 0.15   # USMLE é cheio de pegadinhas, deslizar é normal

    # Equação de Atualização de Bayes (Evidência Observada)
    if is_correct:
        prob_obs = (current_prob * (1 - p_slip)) / ((current_prob * (1 - p_slip)) + ((1 - current_prob) * p_guess))
    else:
        prob_obs = (current_prob * p_slip) / ((current_prob * p_slip) + ((1 - current_prob) * (1 - p_guess)))

    # Aplicação da Taxa de Transição (Aprendizado por ter feito a questão)
    new_prob = prob_obs + (1 - prob_obs) * P_T
    
    # Limita entre 1% e 99% para a matemática não quebrar
    return max(0.01, min(0.99, new_prob))

def classify_tag_bkt(prob):
    """Transforma a probabilidade matemática em um rótulo de Domínio."""
    if prob is None: return MasteryLevel.NEW
    if prob < 0.30: return MasteryLevel.NEW
    elif prob < 0.65: return MasteryLevel.LEARNING
    elif prob < 0.90: return MasteryLevel.CONSOLIDATED
    else: return MasteryLevel.MASTERED

# =========================================================================
# FUNÇÃO PONTE (Mantém a compatibilidade com o scheduler.py e app.py)
# =========================================================================
def classify_tag(correct: int, total: int, threshold: int = 3) -> MasteryLevel:
    """
    Classifica a Tag baseada na proporção de acertos (Lógica Clássica)
    usada pelo scheduler enquanto o banco SQLite não salva a probabilidade (BKT).
    """
    if total == 0:
        return MasteryLevel.DRONE

    if total < threshold:
        return MasteryLevel.NEW

    accuracy = correct / total

    if accuracy < 0.50:
        return MasteryLevel.LEARNING
    elif accuracy < 0.80:
        return MasteryLevel.CONSOLIDATED
    else:
        return MasteryLevel.MASTERED