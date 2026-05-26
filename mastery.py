from enum import Enum

class MasteryLevel(Enum):
    DRONE        = "drone"         # Nunca tocado
    NEW          = "new"           # Tocado, mas abaixo do limiar estatístico
    LEARNING     = "learning"      # Estatisticamente válido, mas precisão baixa
    CONSOLIDATED = "consolidated"  # Precisão média/boa
    MASTERED     = "mastered"      # Precisão excelente e consistente

def classify_tag(correct: int, total: int, threshold: int = 3) -> MasteryLevel:
    """
    Classifica uma Tag baseada no seu volume de histórico e acurácia.
    threshold: Quantidade mínima de tentativas para sair de 'NEW'.
    """
    if total == 0:
        return MasteryLevel.DRONE

    if total < threshold:
        return MasteryLevel.NEW

    accuracy = correct / total

    # Níveis de corte (simples por agora, fáceis de refinar)
    if accuracy < 0.50:
        return MasteryLevel.LEARNING
    elif accuracy < 0.80:
        return MasteryLevel.CONSOLIDATED
    else:
        return MasteryLevel.MASTERED