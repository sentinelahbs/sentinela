"""
Camada de percepção: "onde está a pessoa" e "o que as mãos dela estão fazendo".

Importante: isso NÃO decide sozinho o que é roubo. Ele só extrai sinais
(posição da pessoa, posição das mãos, se está dentro da zona de interesse).
A decisão de "isso é suspeito" fica na camada de regras (pose_rules.py),
que é separada de propósito — assim você consegue ajustar a sensibilidade
sem precisar retreinar nada.

Backend de detecção de pessoa (escolhido por DETECTION_BACKEND):
  - "yolox" (padrão): YOLOX (Megvii), rodando via ONNX Runtime. Licença
    Apache 2.0 — sem exigência de licença comercial. Usar
    DETECTION_MODEL_PATH pra apontar pro .onnx baixado das releases
    oficiais do GitHub, se não for usar o caminho padrão em models/.
  - "yolov8": Ultralytics YOLOv8. Licença AGPL-3.0 — usar em produto
    comercial de código fechado exige Enterprise License paga da
    Ultralytics. NÃO selecionar este backend em instalação nova até essa
    licença estar assinada (ver README do módulo).
  - "picodet": PP-PicoDet (Baidu/PaddleDetection), via ONNX Runtime.
    Licença Apache 2.0 — igual YOLOX, sem exigência de licença comercial.
    Testado só como comparação de velocidade/precisão (ver memória do
    projeto) -- ainda não é o backend padrão de produção.
"""

import os
from dataclasses import dataclass

import cv2
import numpy as np
import mediapipe as mp

DETECTION_BACKEND = os.environ.get("DETECTION_BACKEND", "yolox").lower()
DETECTION_MODEL_PATH = os.environ.get("DETECTION_MODEL_PATH", "")
# Variantes menores do YOLOX (tiny, nano) não usam a entrada 640x640 da
# "s" -- oficialmente 416x416, ver export_onnx.py do repositório. Formato
# esperado: "ALTURA,LARGURA" (mesma ordem de PersonDetectorYoloX.INPUT_SIZE
# -- ambos os tamanhos oficiais são quadrados, então não faz diferença
# prática hoje, mas mantém consistente caso um dia mude). Vazio = usa o
# padrão da classe (640x640, "s"/"m"/"l"/"x").
_raw_input_size = os.environ.get("DETECTION_INPUT_SIZE", "")
DETECTION_INPUT_SIZE = (
    tuple(int(v) for v in _raw_input_size.split(",")) if _raw_input_size else None
)

# Classe "person" no COCO — dataset usado pra treinar tanto o YOLOv8 quanto o YOLOX.
COCO_PERSON_CLASS_ID = 0

# Classes do COCO usadas como sinal de "recipiente" (mochila/bolsa/mala) --
# extração apenas por enquanto, ainda sem regra que use isso (ver memória
# do projeto). O detector já calcula a pontuação de TODAS as 80 classes do
# COCO em cada frame -- extrair essas custa perto de zero a mais de CPU,
# só estava sendo descartado. Testado contra vídeo real: mochila e bolsa
# disparam de verdade (0.37-0.59 de confiança); "mala" nunca apareceu nos
# testes (não é comum em loja), mantida mesmo assim por ser barata.
BAG_CLASS_IDS = {24: "mochila", 26: "bolsa", 28: "mala"}


@dataclass
class PersonSignal:
    person_bbox: tuple          # (x1, y1, x2, y2) em pixels
    hands_px: list               # posições (x, y) em pixels de cada mão detectada
    hands_norm: list             # mesma coisa, normalizado (0-1) — usado nas regras
    confidence: float
    # Referência vertical do tronco (normalizada 0-1 no frame inteiro,
    # mesma convenção de hands_norm) — usada pela regra complementar de
    # desaparecimento (ver HandDisappearanceRule em pose_rules.py) pra
    # saber se uma mão sumiu numa altura "incomum" do corpo (cintura pra
    # baixo) ou "normal" (ombro pra cima). None quando ombro/quadril não
    # está visível com confiança suficiente.
    shoulder_y_norm: "float | None" = None
    hip_y_norm: "float | None" = None


class PersonDetectorYoloV8:
    """Detecta pessoas no quadro com YOLOv8 (modelo pré-treinado, não precisamos
    treinar do zero — 'person' já é uma das classes padrão do COCO)."""

    def __init__(self, model_path: str = "yolov8n.pt", person_conf: float = 0.5):
        from ultralytics import YOLO  # import tardio: só carrega esse peso se este backend for usado

        self.model = YOLO(model_path)
        self.person_conf = person_conf

    def detect_people(self, frame: np.ndarray):
        results = self.model.predict(
            frame, classes=[COCO_PERSON_CLASS_ID], conf=self.person_conf, verbose=False
        )[0]
        boxes = []
        for box in results.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            boxes.append(((int(x1), int(y1), int(x2), int(y2)), conf))
        return boxes

    def detect(self, frame: np.ndarray, bag_conf: float = 0.35):
        """Roda a inferência UMA vez e devolve (pessoas, bolsas) juntas --
        evita chamar predict() duas vezes à toa (ver mesmo padrão nos
        outros dois backends)."""
        classes = [COCO_PERSON_CLASS_ID] + list(BAG_CLASS_IDS)
        results = self.model.predict(frame, classes=classes, conf=bag_conf, verbose=False)[0]
        people, bags = [], []
        for box in results.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            class_id = int(box.cls[0])
            bbox = (int(x1), int(y1), int(x2), int(y2))
            if class_id == COCO_PERSON_CLASS_ID:
                if conf >= self.person_conf:
                    people.append((bbox, conf))
            else:
                bags.append((bbox, conf, BAG_CLASS_IDS[class_id]))
        return people, bags


class PersonDetectorYoloX:
    """Detecta pessoas com YOLOX (Megvii), via ONNX Runtime — sem a exigência
    de licença comercial que o YOLOv8/Ultralytics (AGPL-3.0) tem.

    Espera o export .onnx oficial do repositório Megvii-BaseDetection/YOLOX
    (ex: yolox_s.onnx, entrada 640x640). O pré/pós-processamento aqui segue
    o mesmo formato do demo oficial de ONNX Runtime do YOLOX.
    """

    INPUT_SIZE = (640, 640)  # default -- "s"/"m"/"l"/"x"; tiny/nano usam 416x416
    STRIDES = (8, 16, 32)

    def __init__(self, model_path: str, person_conf: float = 0.5, nms_thr: float = 0.45, input_size: tuple = None):
        import onnxruntime as ort

        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.person_conf = person_conf
        self.nms_thr = nms_thr
        if input_size is not None:
            self.INPUT_SIZE = input_size

    def _preprocess(self, frame: np.ndarray):
        ih, iw = self.INPUT_SIZE
        padded = np.ones((ih, iw, 3), dtype=np.uint8) * 114
        r = min(ih / frame.shape[0], iw / frame.shape[1])
        resized = cv2.resize(
            frame,
            (int(frame.shape[1] * r), int(frame.shape[0] * r)),
            interpolation=cv2.INTER_LINEAR,
        )
        padded[: resized.shape[0], : resized.shape[1]] = resized
        img = padded.transpose(2, 0, 1)[None, :, :, :].astype(np.float32)
        return np.ascontiguousarray(img), r

    def _decode(self, outputs: np.ndarray):
        # Saída do YOLOX é "anchor-free": cada célula do grid já prevê
        # diretamente um box (dx, dy, w, h) relativo a si mesma, em vez de
        # ajustar anchors pré-definidas — por isso somamos a posição do
        # grid e multiplicamos pelo stride pra voltar à escala de pixels.
        grids, strides_arr = [], []
        ih, iw = self.INPUT_SIZE
        for stride in self.STRIDES:
            h, w = ih // stride, iw // stride
            xv, yv = np.meshgrid(np.arange(w), np.arange(h))
            grid = np.stack((xv, yv), 2).reshape(1, -1, 2)
            grids.append(grid)
            strides_arr.append(np.full((1, grid.shape[1], 1), stride))

        grids = np.concatenate(grids, 1)
        strides_arr = np.concatenate(strides_arr, 1)

        outputs[..., :2] = (outputs[..., :2] + grids) * strides_arr
        outputs[..., 2:4] = np.exp(outputs[..., 2:4]) * strides_arr
        return outputs

    def _nms(self, boxes: np.ndarray, scores: np.ndarray):
        x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        areas = (x2 - x1 + 1) * (y2 - y1 + 1)
        order = scores.argsort()[::-1]
        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            w = np.maximum(0.0, xx2 - xx1 + 1)
            h = np.maximum(0.0, yy2 - yy1 + 1)
            inter = w * h
            ovr = inter / (areas[i] + areas[order[1:]] - inter)
            order = order[np.where(ovr <= self.nms_thr)[0] + 1]
        return keep

    def _run_inference(self, frame: np.ndarray):
        """Preprocessa + roda o modelo + decodifica -- extraído do antigo
        detect_people() pra poder ser reaproveitado por detect() sem rodar
        a rede duas vezes (o forward pass é o custo caro, não a extração
        de uma classe a mais dos mesmos outputs)."""
        img, r = self._preprocess(frame)
        outputs = self.session.run(None, {self.input_name: img})[0]
        outputs = self._decode(outputs)[0]
        return outputs, r

    def _extract_class(self, outputs: np.ndarray, r: float, class_id: int, conf_threshold: float) -> list:
        boxes_xywh = outputs[:, :4]
        obj_conf = outputs[:, 4]
        class_scores = outputs[:, 5:]

        scores = obj_conf * class_scores[:, class_id]
        mask = scores > conf_threshold
        if not np.any(mask):
            return []

        boxes_xywh = boxes_xywh[mask]
        scores = scores[mask]

        boxes_xyxy = np.ones_like(boxes_xywh)
        boxes_xyxy[:, 0] = boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2
        boxes_xyxy[:, 1] = boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2
        boxes_xyxy[:, 2] = boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2
        boxes_xyxy[:, 3] = boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2
        boxes_xyxy /= r  # volta da escala do input (640x640) pra escala do frame original

        keep = self._nms(boxes_xyxy, scores)

        result = []
        for i in keep:
            x1, y1, x2, y2 = boxes_xyxy[i]
            result.append(((int(x1), int(y1), int(x2), int(y2)), float(scores[i])))
        return result

    def detect_people(self, frame: np.ndarray):
        outputs, r = self._run_inference(frame)
        return self._extract_class(outputs, r, COCO_PERSON_CLASS_ID, self.person_conf)

    def detect(self, frame: np.ndarray, bag_conf: float = 0.35):
        """Roda a inferência UMA vez e devolve (pessoas, bolsas) juntas —
        ver BAG_CLASS_IDS. NMS roda separado por classe (mesmo princípio
        de detect_people) pra uma bolsa não suprimir a detecção de uma
        pessoa por perto, ou vice-versa."""
        outputs, r = self._run_inference(frame)
        people = self._extract_class(outputs, r, COCO_PERSON_CLASS_ID, self.person_conf)
        bags = []
        for class_id, label in BAG_CLASS_IDS.items():
            for bbox, score in self._extract_class(outputs, r, class_id, bag_conf):
                bags.append((bbox, score, label))
        return people, bags


class PersonDetectorPicoDet:
    """Detecta pessoas com PP-PicoDet (Baidu/PaddleDetection), via ONNX
    Runtime -- Apache 2.0, mesma situação de licença do YOLOX.

    Espera o export .onnx "postprocessado" oficial (NMS já embutido no
    grafo, ver paddledet.bj.bcebos.com/deploy/third_engine/ ou
    configs/picodet/README.md do repositório) -- ex:
    picodet_s_416_lcnet_postprocessed.onnx. Saída já vem com
    [classe, score, x1, y1, x2, y2] por caixa, sem precisar decodificar
    grid/DFL como o YOLOX -- bem menos código de pós-processamento aqui
    por causa disso.

    Pré-processamento segue o reader oficial (picodet_416_reader.yml):
    resize simples pro tamanho de entrada (SEM manter proporção/letterbox,
    diferente do YOLOX), normalização ImageNet (mean/std), e RGB -- OpenCV
    lê BGR, então converte antes de normalizar.
    """

    INPUT_SIZE = (416, 416)
    MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    def __init__(self, model_path: str, person_conf: float = 0.5):
        import onnxruntime as ort

        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.person_conf = person_conf

    def _preprocess(self, frame: np.ndarray):
        ih, iw = self.INPUT_SIZE
        oh, ow = frame.shape[:2]
        resized = cv2.resize(frame, (iw, ih), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        normalized = (rgb - self.MEAN) / self.STD
        img = normalized.transpose(2, 0, 1)[None, :, :, :].astype(np.float32)
        # [alto/original, largura/original] -- é isso que o NMS embutido no
        # grafo usa pra projetar as caixas de volta pra escala do frame
        # original, já que o resize acima não manteve a proporção.
        scale_factor = np.array([[ih / oh, iw / ow]], dtype=np.float32)
        return np.ascontiguousarray(img), scale_factor

    def _run_inference(self, frame: np.ndarray) -> np.ndarray:
        """Roda o modelo e devolve só as linhas VÁLIDAS de
        [classe, score, x1, y1, x2, y2] -- o NMS já vem embutido no grafo
        (ver docstring da classe), cobrindo as 80 classes do COCO de uma
        vez só. Extraído do antigo detect_people() pra dar pra reaproveitar
        em detect() sem rodar a rede duas vezes."""
        img, scale_factor = self._preprocess(frame)
        boxes, valid_count = self.session.run(
            None, {"image": img, "scale_factor": scale_factor}
        )
        n = int(valid_count[0])
        return boxes[:n]

    def detect_people(self, frame: np.ndarray):
        result = []
        for row in self._run_inference(frame):
            class_id, score, x1, y1, x2, y2 = row
            if int(class_id) != COCO_PERSON_CLASS_ID or score < self.person_conf:
                continue
            result.append(((int(x1), int(y1), int(x2), int(y2)), float(score)))
        return result

    def detect(self, frame: np.ndarray, bag_conf: float = 0.35):
        """Roda a inferência UMA vez e devolve (pessoas, bolsas) juntas —
        ver BAG_CLASS_IDS. O NMS embutido no grafo já cobre todas as
        classes de uma vez, então isso é só filtrar o mesmo resultado por
        classe diferente, sem custo extra de inferência.

        Nota: o export "postprocessado" do PicoDet tem um score_threshold
        já embutido no próprio grafo (não configurável daqui) -- se
        bag_conf pedir menos que esse piso, o resultado fica igual ao piso
        do grafo, não ao valor pedido."""
        people, bags = [], []
        for row in self._run_inference(frame):
            class_id, score, x1, y1, x2, y2 = row
            class_id = int(class_id)
            score = float(score)
            bbox = (int(x1), int(y1), int(x2), int(y2))
            if class_id == COCO_PERSON_CLASS_ID:
                if score >= self.person_conf:
                    people.append((bbox, score))
            elif class_id in BAG_CLASS_IDS and score >= bag_conf:
                bags.append((bbox, score, BAG_CLASS_IDS[class_id]))
        return people, bags


def build_person_detector(model_path: str = None, person_conf: float = 0.5):
    """Escolhe o backend de detecção de pessoa pela variável de ambiente
    DETECTION_BACKEND ('yolox', padrão até a licença Enterprise da
    Ultralytics estar assinada, 'yolov8', ou 'picodet')."""
    if DETECTION_BACKEND == "yolox":
        path = model_path or DETECTION_MODEL_PATH or "./models/yolox_s.onnx"
        return PersonDetectorYoloX(path, person_conf=person_conf, input_size=DETECTION_INPUT_SIZE)
    if DETECTION_BACKEND == "picodet":
        path = model_path or DETECTION_MODEL_PATH or "./models/picodet_s_416_postprocessed.onnx"
        return PersonDetectorPicoDet(path, person_conf=person_conf)
    path = model_path or DETECTION_MODEL_PATH or "yolov8n.pt"
    return PersonDetectorYoloV8(path, person_conf=person_conf)


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

    def estimate_pose_signals(self, frame: np.ndarray, bbox: tuple):
        """Roda o MediaPipe Pose UMA vez pra essa pessoa e extrai tanto as
        mãos quanto uma referência vertical do tronco (ombro/quadril) —
        junto de propósito na mesma chamada: MediaPipe já calcula os 33
        pontos numa única passada, então extrair mais pontos do mesmo
        resultado não roda a rede de novo, é só ler mais índices do
        array que já existe. Rodar o Pose duas vezes (uma pra mão, outra
        pro tronco) dobraria o custo à toa.

        Retorna (hands_px, shoulder_y_norm, hip_y_norm):
        - hands_px: sempre 2 posições (x, y) em pixels, uma por mão
          (esquerda, direita), None pra mão não visível — em vez de
          omitir da lista. Isso importa porque quem consome isso
          (pose_rules.py) rastreia cada mão separadamente ao longo dos
          frames; se a lista mudasse de tamanho ou ordem, a mão esquerda
          de um frame acabava sendo comparada com a direita do frame
          anterior, e "parada"/"sumiu" nunca acumulava direito.
        - shoulder_y_norm / hip_y_norm: média dos lados visíveis,
          normalizado 0-1 no frame INTEIRO (mesma convenção de
          hands_norm, calculada por PerceptionPipeline.process) — None
          quando nenhum dos dois lados está visível com confiança
          suficiente."""
        x1, y1, x2, y2 = bbox
        crop = frame[max(0, y1):y2, max(0, x1):x2]
        if crop.size == 0:
            return [None, None], None, None

        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        result = self.pose.process(rgb)
        if not result.pose_landmarks:
            return [None, None], None, None

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
                hands.append(None)
                continue
            # posição da mão em pixels absolutos no frame original
            px = x1 + int(lm.x * w)
            py = y1 + int(lm.y * h)
            hands.append((px, py))

        frame_h = frame.shape[0]
        shoulder_y_norm = self._average_landmark_y(
            landmarks,
            [mp.solutions.pose.PoseLandmark.LEFT_SHOULDER, mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER],
            y1, h, frame_h,
        )
        hip_y_norm = self._average_landmark_y(
            landmarks,
            [mp.solutions.pose.PoseLandmark.LEFT_HIP, mp.solutions.pose.PoseLandmark.RIGHT_HIP],
            y1, h, frame_h,
        )
        return hands, shoulder_y_norm, hip_y_norm

    @staticmethod
    def _average_landmark_y(landmarks, landmark_ids, crop_y1: int, crop_h: int, frame_h: int):
        """Média da posição Y (normalizada 0-1 no frame inteiro) dos
        pontos visíveis dentre os informados — usa a média de esquerdo+
        direito quando os dois estão visíveis, ou só um se o outro
        estiver fora do enquadramento/oculto (mais robusto que exigir os
        dois ao mesmo tempo, especialmente em ângulo de CFTV onde um
        lado do corpo fica mais escondido que o outro). None se nenhum
        dos dois estiver visível com confiança suficiente."""
        ys = [
            (crop_y1 + landmarks[lid].y * crop_h) / frame_h
            for lid in landmark_ids
            if landmarks[lid].visibility >= 0.5
        ]
        return sum(ys) / len(ys) if ys else None

    def close(self):
        self.pose.close()


class PerceptionPipeline:
    """Junta detecção de pessoa + pose num único passo por frame."""

    def __init__(self, frame_size: tuple, model_path: str = None, bag_confidence: float = 0.35):
        self.frame_w, self.frame_h = frame_size
        self.person_detector = build_person_detector(model_path)
        self.pose_estimator = HandPoseEstimator()
        self.bag_confidence = bag_confidence

    def process(self, frame: np.ndarray):
        """Retorna (signals, bags). bags é a lista de recipientes
        detectados no frame inteiro (mochila/bolsa/mala, ver
        BAG_CLASS_IDS) -- [(bbox, confidence, label), ...], sem
        associação com uma pessoa específica ainda (isso fica pra quem
        usar esse dado, ex: uma regra futura de "mão foi na direção da
        bolsa"). Por enquanto é só extração -- nenhuma regra usa isso
        ainda (ver memória do projeto)."""
        signals = []
        people, bags = self.person_detector.detect(frame, bag_conf=self.bag_confidence)
        for bbox, conf in people:
            hands_px, shoulder_y_norm, hip_y_norm = self.pose_estimator.estimate_pose_signals(frame, bbox)
            hands_norm = [
                (h[0] / self.frame_w, h[1] / self.frame_h) if h is not None else None
                for h in hands_px
            ]
            signals.append(
                PersonSignal(
                    person_bbox=bbox,
                    hands_px=hands_px,
                    hands_norm=hands_norm,
                    confidence=conf,
                    shoulder_y_norm=shoulder_y_norm,
                    hip_y_norm=hip_y_norm,
                )
            )
        return signals, bags

    def close(self):
        self.pose_estimator.close()
