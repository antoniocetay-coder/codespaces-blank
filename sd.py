from enum import Enum
from fsrs import calcular_retrievability

class MemoryState(Enum):
    CRITICAL = "critical"
    UNSTABLE = "unstable"
    STABLE   = "stable"

class HealthLevel(Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"

def process_sd(stability: float, difficulty: float, elapsed_days: int) -> dict:
    """
    Recebe S, D e dias decorridos. Devolve o estado interpretável agnóstico.
    Usa calcular_retrievability do fsrs.py como fonte única de verdade.
    """
    r = calcular_retrievability(elapsed_days, stability)

    if stability < 2.0 or r < 0.70:
        state = MemoryState.CRITICAL
    elif stability < 5.0:
        state = MemoryState.UNSTABLE
    else:
        state = MemoryState.STABLE

    if r > 0.85 and difficulty < 6.0:
        health = HealthLevel.HIGH
    elif r > 0.70:
        health = HealthLevel.MEDIUM
    else:
        health = HealthLevel.LOW

    return {
        "stability":      round(stability, 4),
        "difficulty":     round(difficulty, 4),
        "state":          state.value,
        "retrievability": round(r, 4),
        "health":         health.value
    }
