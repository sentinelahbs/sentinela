"""
Camada de percepção: "onde está a pessoa" e "o que as mãos dela estão fazendo".

Importante: isso NÃO decide sozinho o que é roubo. Ele só extrai sinais
(posição da pessoa, posição das mãos, se está dentro da zona de interesse).
A decisão de "isso é suspeito" fica na camada de regras (pose_rules.py),
que é separada de propósito — assim você consegue ajustar a sensibilidade
sem precisar retreinar nada.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from ultralytics import YOLO
import mediapipe as mp


@dataclass
class PersonSignal:
    person_bbox: tuple          # (x1, y1, x2, y2) em pixels
    hands_px: list               # posições (x, y) em pixels de cada mão detectada
    hands_norm: list             # mesma coisa, normalizado (0-1) — usado nas regras
    confidence: float


class PersonDetector:
    """Detecta pessoas no quadro com YOLOv8 (modelo pré-treinado, não precisamos
    treinar do zero — 'person' já é uma das classes padrão do COCO)."""

    def __init__(self, model_path: str = "yolov8n.pt", person_conf: float = 0.5):
        self.model = YOLO(model_path)
        self.person_conf = person_conf

    def detect_people(self, frame: np.ndarray):
        results = self.model.predict(
            frame, classes=[0], conf=self.person_conf, verbose=False
        )[0]
        boxes = []
        for box in results.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            boxes.append(((int(x1), int(y1), int(x2), int(y2)), conf))
        return boxes


class HandPoseEstimator:
    """Estima a pose de uma pessoa recortada do quadro, pra saber onde
    estão as mãos dela. Usa MediaPipe Pose — leve o suficiente pra rodar
    em uma box de baixo custo (não precisa de GPU dedicada)."""

    def __init__(self):
        self.pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def estimate_hands(self, frame: np.ndarray, bbox: tuple):
        x1, y1, x2, y2 = bbox
        crop = frame[max(0, y1):y2, max(0, x1):x2]
        if crop.size == 0:
            return []

        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        result = self.pose.process(rgb)
        if not result.pose_landmarks:
            return []

        h, w = crop.shape[:2]
        landmarks = result.pose_landmarks.landmark
        wrist_ids = [
            mp.solutions.pose.PoseLandmark.LEFT_WRIST,
            mp.solutions.pose.PoseLandmark.RIGHT_WRIST,
        ]
        hands = []
        for wid in wrist_ids:
            lm = landmarks[wid]
            if lm.visibility < 0.5:
                continue
            # posição da mão em pixels absolutos no frame original
            px = x1 + int(lm.x * w)
            py = y1 + int(lm.y * h)
            hands.append((px, py))
        return hands

    def close(self):
        self.pose.close()


class PerceptionPipeline:
    """Junta detecção de pessoa + pose num único passo por frame."""

    def __init__(self, frame_size: tuple, model_path: str = "yolov8n.pt"):
        self.frame_w, self.frame_h = frame_size
        self.person_detector = PersonDetector(model_path)
        self.pose_estimator = HandPoseEstimator()

    def process(self, frame: np.ndarray):
        signals = []
        for bbox, conf in self.person_detector.detect_people(frame):
            hands_px = self.pose_estimator.estimate_hands(frame, bbox)
            hands_norm = [
                (px / self.frame_w, py / self.frame_h) for px, py in hands_px
            ]
            signals.append(
                PersonSignal(
                    person_bbox=bbox,
                    hands_px=hands_px,
                    hands_norm=hands_norm,
                    confidence=conf,
                )
            )
        return signals

    def close(self):
        self.pose_estimator.close()
