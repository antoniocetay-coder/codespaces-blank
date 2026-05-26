from enum import Enum

class MemoryState(Enum):
    CRITICAL = "critical"
    UNSTABLE = "unstable"
    STABLE = "stable"

class HealthLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

def calculate_retrievability(stability: float, elapsed_days: int) -> float:
    """
    Fórmula de Retrievability (R) baseada no FSRS.
    R = (1 + t / (9 * S)) ^ -1
    """
    if stability <= 0:
        return 0.0
    return (1 + elapsed_days / (9 * stability)) ** -1

def process_sd(stability: float, difficulty: float, elapsed_days: int) -> dict:
    """
    Recebe S, D e dias decorridos. Devolve o estado interpretável agnóstico.
    """
    r = calculate_retrievability(stability, elapsed_days)

    # Lógica simples para definir o estado de memória (ajustável no futuro)
    if stability < 2.0 or r < 0.70:
        state = MemoryState.CRITICAL
    elif stability < 5.0:
        state = MemoryState.UNSTABLE
    else:
        state = MemoryState.STABLE

    # Lógica simples para definir a "Saúde" (Health) do item
    if r > 0.85 and difficulty < 6.0:
        health = HealthLevel.HIGH
    elif r > 0.70:
        health = HealthLevel.MEDIUM
    else:
        health = HealthLevel.LOW

    return {
        "stability": round(stability, 4),
        "difficulty": round(difficulty, 4),
        "state": state.value,
        "retrievability": round(r, 4),
        "health": health.value
    }