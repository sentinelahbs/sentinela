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

    def apply_calibration(self, zone_points: list, still_frames_threshold: int) -> None:
        """Aplica calibração nova em tempo real, sem recriar o objeto —
        usado por calibration_sync.py quando o backend manda uma zona ou
        threshold atualizado, no meio da operação. De propósito NÃO mexe
        em self.trackers: preserva o estado de rastreamento de quem já
        está em cena, pra não resetar uma detecção em andamento só
        porque a calibração mudou.

        Deixa Polygon() estourar pra quem chamou (calibration_sync.py) —
        aqui é a regra de negócio, não a camada que decide o que fazer
        com um payload de rede malformado."""
        self.zone = Polygon(zone_points) if zone_points else None
        self.still_frames_threshold = still_frames_threshold

    def forget(self, person_id: str) -> None:
        """Chamado quando o tracker (ver tracker.py) dá uma pessoa como
        saída de cena — sem isso, self.trackers cresce sem limite pro
        resto da vida do processo, já que agora cada pessoa nova ganha um
        id que nunca se repete (antes era só um índice reciclado)."""
        self.trackers.pop(person_id, None)


@dataclass
class HandDisappearanceTracker:
    """Acompanha se uma mão que estava dentro da zona de interesse
    'sumiu' (MediaPipe perdeu o rastreamento, visibility caiu) por tempo
    suficiente pra não ser ruído de oclusão momentânea — e, quando some,
    guarda em que região do corpo ela foi vista pela última vez (ver
    HandDisappearanceRule._classify_region)."""
    was_in_zone: bool = False
    last_region: "str | None" = None  # "unusual" | "normal" | None
    missing_frame_count: int = 0

    def update(self, hand_pos_norm, in_zone: bool, region) -> None:
        if hand_pos_norm is not None:
            # mão visível neste frame — guarda o estado mais recente e
            # zera o contador (só conta sumiço CONTÍNUO, mesmo princípio
            # de "parada" zerar quando a mão se move demais na regra
            # principal).
            self.was_in_zone = in_zone
            self.last_region = region
            self.missing_frame_count = 0
            return
        if self.was_in_zone:
            self.missing_frame_count += 1
        else:
            self.missing_frame_count = 0


class HandDisappearanceRule:
    """Regra COMPLEMENTAR à SuspiciousBehaviorRule — mão que estava
    dentro da zona de interesse e desaparece da visão (MediaPipe perde o
    rastreamento) por N frames seguidos, num movimento contínuo pra
    dentro de bolso/cintura/roupa sem parar — o padrão que a regra de
    "mão parada" não pega (furto rápido).

    De propósito NÃO tem o mesmo peso da regra principal quando dispara
    sozinha (ver combine_rule_results() logo abaixo): mão sumir perto de
    uma prateleira é ambíguo por natureza — pode ser o próprio produto/
    prateleira ocluindo a mão numa interação de compra normal, não
    necessariamente bolso. Por isso esse sinal sozinho ainda registra o
    evento (confiança baixa, pro dono observar casos reais e calibrar),
    e só vira alerta de confiança alta quando bate JUNTO com a regra
    principal disparando pra mesma pessoa."""

    def __init__(self, zone_points: list, missing_frames_threshold: int):
        self.zone = Polygon(zone_points) if zone_points else None
        self.missing_frames_threshold = missing_frames_threshold
        self.trackers = {}  # id da pessoa -> list[HandDisappearanceTracker]

    def _in_zone(self, pos_norm: tuple) -> bool:
        if self.zone is None:
            return True
        return self.zone.contains(Point(pos_norm))

    @staticmethod
    def _classify_region(hand_y_norm: float, shoulder_y_norm, hip_y_norm):
        """"Incomum" = mão na altura do quadril ou abaixo (cintura,
        bolso, lateral do corpo). "Normal" = na altura do ombro ou acima
        (perto do rosto/cabeça — ajeitando cabelo, coçando o nariz).
        Entre ombro e quadril (tronco) fica de propósito como None, nem
        incomum nem normal — lado conservador, evita marcar como
        incomum um gesto no peito (ajeitar blusa, crachá) que não é o
        padrão que estamos tentando pegar. Também None sem ombro/quadril
        confiável (pessoa cortada na borda do quadro, ângulo ruim)."""
        if shoulder_y_norm is None or hip_y_norm is None:
            return None
        if hand_y_norm >= hip_y_norm:
            return "unusual"
        if hand_y_norm <= shoulder_y_norm:
            return "normal"
        return None

    def evaluate(self, person_id: str, signal) -> tuple:
        """Retorna (fired, reason). Sem confidence aqui de propósito —
        quem decide o peso final é combine_rule_results(), que sabe se
        essa regra disparou sozinha ou junto com a principal."""
        trackers = self.trackers.setdefault(person_id, [])
        while len(trackers) < len(signal.hands_norm):
            trackers.append(HandDisappearanceTracker())

        fired_unusual = False
        for slot, hand_pos in enumerate(signal.hands_norm):
            tracker = trackers[slot]
            in_zone = self._in_zone(hand_pos) if hand_pos is not None else False
            region = (
                self._classify_region(hand_pos[1], signal.shoulder_y_norm, signal.hip_y_norm)
                if hand_pos is not None else None
            )
            tracker.update(hand_pos, in_zone, region)

            if tracker.missing_frame_count >= self.missing_frames_threshold and tracker.last_region == "unusual":
                fired_unusual = True

        if not fired_unusual:
            return False, None

        reason = (
            "Mão desapareceu da visão em região incomum do corpo "
            "(cintura/lateral) após estar na zona de interesse"
        )
        return True, reason

    def apply_calibration(self, zone_points: list, missing_frames_threshold: int) -> None:
        """Mesmo princípio de SuspiciousBehaviorRule.apply_calibration —
        hot-reload sem recriar o objeto, preserva self.trackers. Hoje
        sempre chamado com o mesmo threshold da regra principal (ver
        main.py) — essa regra ainda não tem calibração remota própria."""
        self.zone = Polygon(zone_points) if zone_points else None
        self.missing_frames_threshold = missing_frames_threshold

    def forget(self, person_id: str) -> None:
        self.trackers.pop(person_id, None)


# Confiança usada quando a regra de desaparecimento dispara SOZINHA (sem
# a regra principal também disparar pra mesma pessoa) — de propósito
# abaixo do min_confidence_to_alert padrão (0.55, ver config.py), pra
# esses eventos ficarem registrados sem virar alerta de cara; o dono
# decide se quer baixar o threshold da câmera pra começar a ver esses
# casos e calibrar antes de confiar neles com o mesmo peso da regra
# principal.
DISAPPEARANCE_ALONE_CONFIDENCE = 0.35

# Quanto a confiança da regra principal sobe quando as duas regras
# disparam juntas pra mesma pessoa — sinal corroborado, mais confiável
# que qualquer uma das duas sozinha.
COMBINED_CONFIDENCE_BOOST = 0.15


def combine_rule_results(still_result: tuple, disappearance_result: tuple) -> tuple:
    """Junta o resultado da regra principal (mão parada, SuspiciousBehaviorRule)
    com o da regra complementar (mão desaparece em região incomum,
    HandDisappearanceRule) numa única decisão de alerta pra mesma
    pessoa/frame. Ver as docstrings das duas classes pro motivo dos
    pesos serem assimétricos."""
    still_fired, still_confidence, still_reason = still_result
    disappear_fired, disappear_reason = disappearance_result

    if still_fired and disappear_fired:
        combined_confidence = min(still_confidence + COMBINED_CONFIDENCE_BOOST, 0.99)
        combined_reason = f"{still_reason} + {disappear_reason}"
        return True, round(combined_confidence, 2), combined_reason

    if still_fired:
        return True, still_confidence, still_reason

    if disappear_fired:
        return True, DISAPPEARANCE_ALONE_CONFIDENCE, disappear_reason

    return False, 0.0, None
