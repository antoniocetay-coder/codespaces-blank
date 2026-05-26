import math
from datetime import datetime

# Pesos matemáticos padrão do algoritmo FSRS v4
w = [
    0.4, 0.6, 2.4, 5.8,      # [0-3] Initial Stability (Again, Hard, Good, Easy)
    4.93, 0.94, 0.86, 0.01,  # [4-7] Dificuldade (D)
    1.49, 0.14, 0.94,        # [8-10] Estabilidade em caso de Sucesso
    2.18, 0.05, 0.34, 1.26,  # [11-14] Estabilidade em caso de Falha (Lapse)
    0.29, 2.61               # [15-16] Multiplicadores para Hard e Easy
]

def calcular_retrievability(elapsed_days, stability):
    """ Calcula a chance atual (R) de lembrar do card """
    if stability <= 0: return 0.0
    return (1 + elapsed_days / (9 * stability)) ** -1

def init_ds(grade):
    """ Inicia Dificuldade (D) e Estabilidade (S) no primeiro review """
    s = w[grade - 1]
    d = w[4] - w[5] * (grade - 3)
    d = max(1.0, min(10.0, d)) # Dificuldade sempre entre 1 e 10
    return d, s

def calcular_fsrs(grade, d, s, elapsed_days, reps, lapses):
    """
    Parâmetros:
    - grade: 1 (Again), 2 (Hard), 3 (Good), 4 (Easy)
    - d: Dificuldade atual
    - s: Estabilidade atual
    - elapsed_days: dias desde a última revisão
    """
    
    r = calcular_retrievability(elapsed_days, s)

    if reps == 0:
        d, s = init_ds(grade)
        reps = 1
        lapses = 1 if grade == 1 else 0
    else:
        if grade == 1:
            # Novamente (Again) -> Falha
            lapses += 1
            s = w[11] * math.pow(d, -w[12]) * (math.pow(s + 1, w[13]) - 1) * math.exp(w[14] * (1 - r))
        else:
            # Sucesso (Hard, Good, Easy)
            s = s * (1 + math.exp(w[8]) * (11 - d) * math.pow(s, -w[9]) * (math.exp(w[10] * (1 - r)) - 1))
            if grade == 2:
                s *= w[15] # Penalidade se for Hard
            elif grade == 4:
                s *= w[16] # Bônus de memória se for Easy
        
        # Ajusta e estabiliza a Dificuldade (D)
        d = d - w[6] * (grade - 3)
        d = max(1.0, min(10.0, d))
        d = d + w[7] * (5 - d) # Mean reversion
        reps += 1

    # Request Retention: Mantém 90% de retenção alvo
    request_retention = 0.90
    interval = max(1, round(s * 9 * (1 / request_retention - 1)))

    return d, s, r, interval, reps, lapses