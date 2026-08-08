"""
Camada de regras: transforma sinais de pose em "isso merece um alerta?".

De propósito NÃO é um classificador de deep learning treinado pra dizer
"isso é roubo". É heurística explicável — o que tem duas vantagens práticas:

1. Você consegue calibrar e explicar por que um alerta disparou (importante
   pro dashboard, pra auditoria, e pra debugar falso positivo).
2. Dá pra ajustar por câmera/loja sem precisar re-treinar nada.

Regra usada aqui como ponto de partida: mão dentro da zona de interesse
(ex: perto de uma prateleira de alto valor) e praticamente parada por N
frames seguidos — padrão consistente com "pegando e escondendo algo",
mas sem nenhuma pretensão de certeza — por isso o output tem confidence,
não um booleano puro, e por isso a revisão humana é obrigatória depois.
"""

from dataclasses import dataclass, field
from shapely.geometry import Point, Polygon


@dataclass
class HandTracker:
    """Mantém o histórico de posição de uma mão ao longo dos frames pra
    saber se ela ficou 'parada' dentro da zona por tempo suficiente."""
    positions: list = field(default_factory=list)  # janela deslizante (x, y)
    still_frame_count: int = 0
    max_movement_norm: float = 0.015  # quanto a mão pode "tremer" e ainda contar como parada

    def update(self, pos_norm: tuple, in_zone: bool):
        if not in_zone:
            self.still_frame_count = 0
            self.positions.clear()
            return

        if self.positions:
            last = self.positions[-1]
            moved = ((pos_norm[0] - last[0]) ** 2 + (pos_norm[1] - last[1]) ** 2) ** 0.5
            if moved <= self.max_movement_norm:
                self.still_frame_count += 1
            else:
                self.still_frame_count = 0
        self.positions.append(pos_norm)
        if len(self.positions) > 90:  # não deixa crescer pra sempre
            self.positions.pop(0)


class SuspiciousBehaviorRule:
    def __init__(self, zone_points: list, still_frames_threshold: int):
        self.zone = Polygon(zone_points) if zone_points else None
        self.still_frames_threshold = still_frames_threshold
        # cada pessoa tem uma lista de trackers, um por "posição" na lista de
        # mãos (esquerda, direita) — sem isso, quando as duas mãos aparecem
        # no quadro, a posição de uma acabava sendo comparada com a da outra
        # no frame seguinte, e "parada" nunca acumulava direito.
        self.trackers = {}  # id da pessoa -> list[HandTracker]

    def _in_zone(self, pos_norm: tuple) -> bool:
        if self.zone is None:
            return True  # sem zona configurada = zona é o quadro inteiro
        return self.zone.contains(Point(pos_norm))

    def evaluate(self, person_id: str, hands_norm: list):
        """Retorna (is_suspicious, confidence, reason) para uma pessoa neste frame."""
        person_trackers = self.trackers.setdefault(person_id, [])
        while len(person_trackers) < len(hands_norm):
            person_trackers.append(HandTracker())

        best_still_count = 0
        for slot, hand_pos in enumerate(hands_norm):
            tracker = person_trackers[slot]
            if hand_pos is None:
                tracker.still_frame_count = 0
                tracker.positions.clear()
                continue
            in_zone = self._in_zone(hand_pos)
            tracker.update(hand_pos, in_zone)
            best_still_count = max(best_still_count, tracker.still_frame_count)

        if best_still_count < self.still_frames_threshold:
            return False, 0.0, None

        # confiança sobe conforme o comportamento persiste além do threshold,
        # até um teto — isso vira o "score" mostrado no dashboard pro gestor
        overshoot = best_still_count - self.still_frames_threshold
        confidence = min(0.55 + overshoot * 0.01, 0.97)
        reason = "Mão parada dentro da zona de interesse por tempo prolongado"
        return True, round(confidence, 2), reason

    def forget(self, person_id: str) -> None:
        """Chamado quando o tracker (ver tracker.py) dá uma pessoa como
        saída de cena — sem isso, self.trackers cresce sem limite pro
        resto da vida do processo, já que agora cada pessoa nova ganha um
        id que nunca se repete (antes era só um índice reciclado)."""
        self.trackers.pop(person_id, None)
