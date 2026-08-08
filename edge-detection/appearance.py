"""
Assinatura barata de aparência: histograma de cor HSV do recorte da
pessoa. Não é re-identificação de verdade (sem modelo treinado, sem
embedding) — só o bastante pra distinguir "provavelmente a mesma pessoa"
de "provavelmente pessoas diferentes" entre duas câmeras vizinhas, sem
pesar quase nada no orçamento de CPU já apertado (ver detector.py).
"""

import cv2
import numpy as np

# H (matiz) e S (saturação) capturam cor de roupa melhor que V
# (luminosidade) — V varia muito entre câmeras com iluminação/exposição
# diferentes mesmo olhando pra mesma pessoa, por isso fica de fora.
_H_BINS = 30
_S_BINS = 32


def color_signature(frame: np.ndarray, bbox: tuple) -> bytes:
    """bbox em pixels (x1, y1, x2, y2), mesmo formato de PersonSignal.person_bbox
    (ver detector.py). Recorte inválido (fora do frame, tamanho zero)
    volta como b"" — signature_distance trata isso como "nunca casa"."""
    x1, y1, x2, y2 = bbox
    crop = frame[max(0, y1):y2, max(0, x1):x2]
    if crop.size == 0:
        return b""
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [_H_BINS, _S_BINS], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
    return hist.astype(np.float32).tobytes()


def signature_distance(sig_a: bytes, sig_b: bytes) -> float:
    """0 = idêntico, 1 = totalmente diferente (distância de Bhattacharyya).
    Assinatura vazia nunca "casa" com nada — devolve a distância máxima
    em vez de estourar exceção ao tentar comparar."""
    if not sig_a or not sig_b:
        return 1.0
    hist_a = np.frombuffer(sig_a, dtype=np.float32).reshape(_H_BINS, _S_BINS)
    hist_b = np.frombuffer(sig_b, dtype=np.float32).reshape(_H_BINS, _S_BINS)
    return float(cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_BHATTACHARYYA))
