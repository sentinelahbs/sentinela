"""
Tracker por IOU: mantém a identidade de uma pessoa entre frames da MESMA
câmera. Sem isso, person_id era só o índice da pessoa na lista de
detecções daquele frame (ver histórico em main.py/pose_rules.py) — se a
ordem mudasse de um frame pro outro (alguém entra no meio da cena, por
exemplo), o histórico de "mão parada" de pose_rules.py virava lixo, e não
tinha como saber se uma pessoa específica saiu do quadro — informação que
a correlação entre câmeras (ver camera_neighbors no backend) precisa.

Deliberadamente NÃO é ByteTrack/DeepSORT: sem re-identificação por
aparência, sem filtro de Kalman — só sobreposição de caixa (IOU) entre
frames consecutivos, com um fallback por distância de centro quando o
IOU zera. Esse fallback existe porque a câmera roda a só ~1-1.5 frame/s
no hardware alvo sem GPU (ver config.py) — nesse intervalo entre frames
processados, alguém andando pode deslocar o bbox o bastante pra IOU puro
nunca casar, mesmo sendo claramente a mesma pessoa.
"""

from dataclasses import dataclass


def _iou(box_a: tuple, box_b: tuple) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    intersection = iw * ih
    if intersection == 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def _center(box: tuple) -> tuple:
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, (y1 + y2) / 2)


@dataclass
class Track:
    track_id: int
    bbox: tuple
    missed_frames: int = 0
    exited_frame_edge: bool = False


class IouTracker:
    """Chame update(bboxes, frame_size) uma vez por frame, passando os
    bboxes na mesma ordem dos sinais de detecção daquele frame. Retorna
    uma lista de track_id na MESMA ordem — quem chama só precisa fazer
    zip(track_ids, signals). Depois de cada update(), ended_tracks tem os
    tracks que sumiram por frames demais seguidos (pruning) — quem chama
    deve usar isso pra limpar qualquer estado próprio guardado por
    person_id (ex: SuspiciousBehaviorRule.forget), senão esse estado
    cresce sem limite pro resto da vida do processo."""

    def __init__(
        self,
        iou_threshold: float = 0.3,
        max_missed_frames: int = 3,
        edge_margin_norm: float = 0.03,
        centroid_fallback_norm: float = 0.15,
    ):
        self.iou_threshold = iou_threshold
        self.max_missed_frames = max_missed_frames
        self.edge_margin_norm = edge_margin_norm
        self.centroid_fallback_norm = centroid_fallback_norm
        self._tracks: dict[int, Track] = {}
        self._next_id = 1
        self.ended_tracks: list[Track] = []

    def update(self, bboxes: list, frame_size: tuple) -> list:
        self.ended_tracks = []
        unmatched_track_ids = set(self._tracks.keys())

        # Guloso por melhor score primeiro — evita duas detecções novas
        # disputarem o mesmo track antigo de forma arbitrária.
        pairs = []
        for det_idx, bbox in enumerate(bboxes):
            for track_id in unmatched_track_ids:
                score = self._match_score(bbox, self._tracks[track_id].bbox, frame_size)
                if score > 0:
                    pairs.append((score, det_idx, track_id))
        pairs.sort(key=lambda p: p[0], reverse=True)

        assigned = [None] * len(bboxes)
        matched_dets = set()
        for score, det_idx, track_id in pairs:
            if det_idx in matched_dets or track_id not in unmatched_track_ids:
                continue
            track = self._tracks[track_id]
            track.bbox = bboxes[det_idx]
            track.missed_frames = 0
            assigned[det_idx] = track_id
            matched_dets.add(det_idx)
            unmatched_track_ids.discard(track_id)

        for det_idx, bbox in enumerate(bboxes):
            if assigned[det_idx] is None:
                track_id = self._next_id
                self._next_id += 1
                self._tracks[track_id] = Track(track_id=track_id, bbox=bbox)
                assigned[det_idx] = track_id

        for track_id in unmatched_track_ids:
            track = self._tracks[track_id]
            track.missed_frames += 1
            if track.missed_frames > self.max_missed_frames:
                track.exited_frame_edge = self._touches_edge(track.bbox, frame_size)
                self.ended_tracks.append(track)
                del self._tracks[track_id]

        return assigned

    def _match_score(self, bbox_a: tuple, bbox_b: tuple, frame_size: tuple) -> float:
        iou_score = _iou(bbox_a, bbox_b)
        if iou_score >= self.iou_threshold:
            return iou_score

        # Fallback só entra quando o IOU não achou nada (score 0) — se já
        # existe alguma sobreposição mas abaixo do threshold, mais vale
        # tratar como pessoas diferentes do que arriscar juntar duas
        # pessoas próximas uma da outra por proximidade de centro.
        if iou_score > 0:
            return 0.0

        w, h = frame_size
        diagonal = (w ** 2 + h ** 2) ** 0.5
        if diagonal == 0:
            return 0.0
        ca, cb = _center(bbox_a), _center(bbox_b)
        dist_norm = ((ca[0] - cb[0]) ** 2 + (ca[1] - cb[1]) ** 2) ** 0.5 / diagonal
        if dist_norm > self.centroid_fallback_norm:
            return 0.0
        # Score baixo de propósito (nunca >= iou_threshold): matches por
        # IOU real sempre ganham do fallback por centro no sort acima.
        # max(..., epsilon): dist_norm pode empatar exatamente com o
        # threshold (caso de borda) — sem o piso, esse match legítimo
        # sairia com score 0.0 e o filtro "score > 0" em update() descartava
        # o par inteiro, como se não tivesse achado candidato nenhum.
        return max(self.centroid_fallback_norm - dist_norm, 1e-9)

    def _touches_edge(self, bbox: tuple, frame_size: tuple) -> bool:
        w, h = frame_size
        x1, y1, x2, y2 = bbox
        margin_x, margin_y = w * self.edge_margin_norm, h * self.edge_margin_norm
        return x1 <= margin_x or y1 <= margin_y or x2 >= w - margin_x or y2 >= h - margin_y
