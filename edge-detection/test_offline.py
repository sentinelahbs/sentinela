"""
Modo de teste offline do pipeline de detecção — roda o MESMO código que
roda na box (YOLOX + MediaPipe Pose + pose_rules.py, incluindo a regra
de desaparecimento) contra um arquivo de vídeo gravado, em vez de câmera
ao vivo. Serve pra testar/calibrar as regras usando vídeos de teste
(ex: datasets públicos de comportamento suspeito em loja) antes de
confiar nelas em produção.

Não usa RollingCapture (capture.py) de propósito: aquela classe foi
construída pra stream ao vivo instável (RTSP de DVR) e tem duas coisas
que quebram com um arquivo finito — trata fim-de-arquivo como falha de
conexão e tenta "reconectar" reabrindo o mesmo arquivo do zero (loop
infinito, nunca processaria o vídeo inteiro e pararia sozinho), e limita
a taxa de leitura em tempo real de parede (processar levaria o tempo
real de duração do vídeo, em vez da velocidade que a CPU aguentar).
Tudo mais é reaproveitado sem modificação: PerceptionPipeline (detector.py),
IouTracker (tracker.py), SuspiciousBehaviorRule/HandDisappearanceRule/
combine_rule_results (pose_rules.py).

Uso:
    python test_offline.py video.mp4
    python test_offline.py video.mp4 --zone "[[0.1,0.35],[0.9,0.35],[0.9,0.98],[0.1,0.98]]"
    python test_offline.py video.mp4 --still-frames-threshold 8 --frame-skip 2
    python test_offline.py video.mp4 --no-annotated-video   # só o log, mais rápido

Por padrão não se conecta a backend nem nada de produção — os resultados
(CSV + vídeo anotado) ficam só no disco. Opcionalmente (--send-to-backend),
manda os eventos que teriam gerado alerta de verdade pro backend, com
clipe real (mesma rota que a box de produção usa, alert_client.py) —
pra ver os alertas aparecendo no dashboard/admin em vez de só ler CSV:

    python test_offline.py video.mp4 --send-to-backend \
        --store-id 4364f77e-... --api-key gYeDT... --camera-label "Teste offline"

Também gera um relatório extra (--no-appearance-grouping desliga): o
IouTracker (tracker.py) é só geométrico (IOU + distância de centro), então
uma mesma pessoa que fica oculta por mais que alguns frames, ou anda rápido
demais entre dois frames processados, vira um track_id novo — o vídeo de
teste real usado nesta sessão gerou ~10 track_ids pra poucas pessoas de
verdade. Esse relatório usa a assinatura de cor (appearance.py, já usada
pra correlação ENTRE câmeras) pra agrupar, DEPOIS que o vídeo inteiro foi
processado, quais track_ids provavelmente são a mesma pessoa reaparecendo
— só pra leitura/calibração (arquivo "<vídeo>_pessoas_agrupadas.csv" e um
resumo no log). É heurístico (roupa parecida pode enganar) e NUNCA afeta
regras, cooldown, destaque no vídeo anotado ou envio pro backend.
"""

import argparse
import collections
import csv
import json
import logging
import os
import time

import cv2

from detector import PerceptionPipeline, DETECTION_BACKEND
from tracker import IouTracker
from clip_recorder import ClipRecorder, _make_faststart
from alert_client import AlertClient
from pose_rules import SuspiciousBehaviorRule, HandDisappearanceRule, combine_rule_results
from appearance import color_signature, signature_distance
from config import _DEFAULT_ZONE, _DEFAULT_HAND_STILL_FRAMES, _DEFAULT_MIN_CONFIDENCE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("test_offline")

# Quantos frames o destaque visual de "regra disparou" fica marcado no
# vídeo anotado depois do frame que disparou — só pra dar tempo de ver
# ao pausar/avançar quadro a quadro, o disparo em si é instantâneo.
HIGHLIGHT_HOLD_SECONDS = 1.0

ZONE_COLOR = (0, 210, 255)       # amarelo (BGR) — contorno da zona de interesse
EXCLUSION_ZONE_COLOR = (128, 0, 255)  # rosa/magenta — contorno de área excluída (ex: freezer)
BAG_BOX_COLOR = (255, 140, 0)          # azul (BGR) — mochila/bolsa/mala detectada (só visualização, sem regra ainda)
HAND_IN_ZONE_COLOR = (0, 220, 0)     # verde — mão visível dentro da zona
HAND_OUT_ZONE_COLOR = (160, 160, 160)  # cinza — mão visível fora da zona
SHOULDER_LINE_COLOR = (255, 200, 0)   # ciano — referência de ombro
HIP_LINE_COLOR = (200, 0, 200)        # magenta — referência de quadril
ALERT_BOX_COLOR = (0, 0, 255)         # vermelho — destaque quando uma regra dispara
PERSON_BOX_COLOR = (0, 200, 0)        # verde — pessoa detectada, nenhuma regra ativa no momento

# _make_faststart (corrige o índice do MP4 pro início do arquivo, ver
# clip_recorder.py pro motivo completo) é reaproveitada de lá — write_clip
# já chama sozinha pra todo clipe de alerta; aqui só precisa ser chamada
# à parte pro vídeo anotado, que não passa por ClipRecorder.


# Mesmo valor de COOLDOWN_SECONDS em main.py — evita mandar um alerta novo
# pro backend a cada frame enquanto a mesma pessoa continua disparando a
# regra (ex: parada 10s a 3fps dispararia ~24 vezes sem isso). Baseado em
# TEMPO DE VÍDEO (frame_index / fps do vídeo), não tempo de execução do
# script — processar rápido não deve "furar" o cooldown que existiria na
# câmera real rodando em tempo real.
COOLDOWN_SECONDS = 60


class _CaptureAdapter:
    """Adaptador mínimo pra reaproveitar ClipRecorder.write_clip (pensado
    originalmente pra RollingCapture ao vivo, só usa capture.frames()) em
    cima do mesmo cv2.VideoCapture que este script já está lendo
    sequencialmente. Só entrega os próximos frames do arquivo, sem
    reconexão — se o arquivo acabar no meio da gravação do clipe, o
    generator simplesmente para (write_clip já lida bem com isso, seu
    loop só continua enquanto capture.frames() ainda produzir algo).

    Ritmo de entrega throttlado em 1/fps_target de propósito: write_clip
    decide quando parar de gravar por TEMPO DE PAREDE decorrido
    (post_event_seconds), não por contagem de frames — sem throttle, ler
    o arquivo o mais rápido possível faria esse relógio de parede passar
    quase instantaneamente e o clipe sair com poucos frames (ou, se lido
    rápido demais, um clipe MUITO mais longo que o pretendido — muito
    mais frames do que post_event_seconds*fps_target representa)."""

    def __init__(self, cap, fps_target: float):
        self.cap = cap
        self.min_interval = 1.0 / fps_target if fps_target > 0 else 0.0
        # Quantos frames este adaptador consumiu do cap -- quem chama
        # precisa somar isso no próprio contador de frame_index depois,
        # senão o índice do loop principal fica dessincronizado da
        # posição real do arquivo (o adaptador lê direto do mesmo cap
        # que o loop principal também está lendo).
        self.frames_yielded = 0

    def frames(self):
        while True:
            ok, frame = self.cap.read()
            if not ok:
                return
            self.frames_yielded += 1
            yield time.time(), frame
            if self.min_interval > 0:
                time.sleep(self.min_interval)


def parse_args():
    parser = argparse.ArgumentParser(description="Testa o pipeline de detecção offline contra um arquivo de vídeo.")
    parser.add_argument("video_path", help="Caminho do arquivo de vídeo de teste")
    parser.add_argument(
        "--zone", default=json.dumps(_DEFAULT_ZONE),
        help='Zona de interesse, JSON de pares [x,y] normalizados 0-1. Default: mesma zona padrão da box.',
    )
    parser.add_argument(
        "--exclusion-zone", default="[]",
        help=(
            "Sub-área(s) DENTRO da zona de interesse a ignorar (ex: freezer/prateleira baixa, onde "
            "reabastecer parece 'esconder algo' pra essas regras). JSON de lista de zonas, cada uma no "
            "mesmo formato de --zone: '[[[0.0,0.6],[0.3,0.6],[0.3,0.98],[0.0,0.98]]]'. Default: nenhuma."
        ),
    )
    parser.add_argument(
        "--still-frames-threshold", type=int, default=_DEFAULT_HAND_STILL_FRAMES,
        help=f"Frames seguidos de mão parada pra disparar a regra principal (default: {_DEFAULT_HAND_STILL_FRAMES}, igual à box).",
    )
    parser.add_argument(
        "--missing-frames-threshold", type=int, default=None,
        help="Frames seguidos de mão ausente pra disparar a regra de desaparecimento (default: igual a --still-frames-threshold, mesmo padrão usado em main.py).",
    )
    parser.add_argument(
        "--min-confidence", type=float, default=_DEFAULT_MIN_CONFIDENCE,
        help=f"Confiança mínima pra um evento contar como 'teria alertado' no log (default: {_DEFAULT_MIN_CONFIDENCE}, igual à box).",
    )
    parser.add_argument(
        "--bag-confidence", type=float, default=0.35,
        help=(
            "Confiança mínima pra desenhar uma mochila/bolsa/mala detectada no vídeo anotado "
            "(default: 0.35). Só visualização por enquanto -- nenhuma regra usa isso ainda."
        ),
    )
    parser.add_argument(
        "--no-show-bags", action="store_true",
        help="Não desenha as mochilas/bolsas/malas detectadas no vídeo anotado (ligado por padrão).",
    )
    parser.add_argument(
        "--frame-skip", type=int, default=1,
        help=(
            "Processa 1 a cada N frames (default: 1 = nenhum pulado, processa TODOS — "
            "os thresholds são contados em frames, não em segundos, então o padrão bate "
            "exatamente com o que roda na câmera real. Só aumente se a máquina de teste "
            "não aguentar processar em tempo hábil; o log deixa avisado quando isso muda "
            "o fps efetivo)."
        ),
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Pasta pra salvar o log CSV e o vídeo anotado (default: mesma pasta do vídeo de entrada).",
    )
    parser.add_argument(
        "--no-annotated-video", action="store_true",
        help="Não gera o vídeo anotado, só o log CSV (mais rápido).",
    )

    backend = parser.add_argument_group(
        "envio pro backend (opcional)",
        "Manda os eventos que teriam gerado alerta (confiança >= --min-confidence) pro backend "
        "de verdade, com clipe real -- mesma rota que a box de produção usa (alert_client.py). "
        "Nada disso roda a menos que --send-to-backend seja passado.",
    )
    backend.add_argument(
        "--send-to-backend", action="store_true",
        help="Ativa o envio dos eventos pro backend. Exige --store-id e --api-key.",
    )
    backend.add_argument(
        "--store-id", default=None,
        help="ID da loja de teste (você descobre com GET /v1/edge/whoami usando --api-key).",
    )
    backend.add_argument(
        "--api-key", default=None,
        help="X-API-Key da loja de teste (mostrada uma única vez na criação da loja no dashboard).",
    )
    backend.add_argument(
        "--api-base-url", default="https://api.vigialoja.com.br",
        help="URL do backend (default: produção — não existe ambiente de dev separado hoje).",
    )
    backend.add_argument(
        "--camera-id", default=None,
        help="ID de uma câmera cadastrada nessa loja, se quiser o alerta vinculado a uma câmera específica (opcional).",
    )
    backend.add_argument(
        "--camera-label", default=None,
        help="Rótulo mostrado no dashboard pro alerta (default: 'Teste offline — <nome do vídeo>').",
    )
    backend.add_argument(
        "--pre-event-seconds", type=int, default=5,
        help="Quanto de vídeo (em segundos de vídeo) incluir ANTES do momento do disparo no clipe (default: 5, igual ao padrão de StoreConfig).",
    )
    backend.add_argument(
        "--post-event-seconds", type=int, default=20,
        help="Quanto incluir DEPOIS do disparo no clipe (default: 20, igual ao padrão de StoreConfig).",
    )

    grouping = parser.add_argument_group(
        "agrupamento por aparência (heurístico, opcional)",
        "Depois de processar o vídeo inteiro, tenta reconhecer quando dois track_ids do IouTracker "
        "(tracker.py, só geométrico -- sem re-identificação por aparência) provavelmente são a MESMA "
        "pessoa reaparecendo, usando a assinatura de cor de roupa (appearance.py, mesma lógica já usada "
        "pra correlação entre câmeras). Só gera um relatório extra pra leitura -- nunca muda o que as "
        "regras avaliam, o cooldown, o destaque no vídeo anotado ou o que é mandado pro backend.",
    )
    grouping.add_argument(
        "--no-appearance-grouping", action="store_true",
        help="Desliga o relatório de agrupamento por aparência (ligado por padrão -- custo desprezível, ~0.3ms/pessoa/frame).",
    )
    grouping.add_argument(
        "--appearance-max-gap-seconds", type=float, default=5.0,
        help="Só tenta religar dois track_ids se o intervalo entre o fim de um e o início do outro (tempo de vídeo) for até isso (default: 5.0s).",
    )
    grouping.add_argument(
        "--appearance-max-move-norm", type=float, default=0.35,
        help="Só tenta religar se o centro da caixa não se deslocou mais que isso, como fração da diagonal do frame (default: 0.35 -- mais generoso que o fallback de centro do tracker, 0.15, porque aqui pode ter passado mais tempo).",
    )
    grouping.add_argument(
        "--appearance-max-color-distance", type=float, default=0.35,
        help="Distância máxima de assinatura de cor (Bhattacharyya, 0=idêntica, 1=totalmente diferente) pra aceitar como a mesma pessoa (default: 0.35 -- mais rígido que o 0.4 usado na correlação entre câmeras, já que a mesma câmera não muda de iluminação).",
    )
    grouping.add_argument(
        "--appearance-min-duration-seconds", type=float, default=2.0,
        help=(
            "Pessoas prováveis que aparecem (do primeiro ao último track_id do grupo) por menos que isso "
            "são marcadas como possível ruído do detector/tracker no relatório -- um fragmento de <1s "
            "raramente é uma pessoa de verdade entrando e saindo de quadro. Não remove a linha do CSV, "
            "só marca e ajusta a contagem 'provável' no resumo do log (default: 2.0s, 0 desliga o filtro)."
        ),
    )

    args = parser.parse_args()
    if args.send_to_backend and not (args.store_id and args.api_key):
        parser.error("--send-to-backend precisa de --store-id e --api-key")
    return args


def _in_zone_color(hand_pos, zone_rule):
    if hand_pos is None:
        return None
    return HAND_IN_ZONE_COLOR if zone_rule._in_zone(hand_pos) else HAND_OUT_ZONE_COLOR


def _draw_zone(frame, zone_points, w, h, color=ZONE_COLOR):
    if not zone_points:
        return
    pts = [(int(x * w), int(y * h)) for x, y in zone_points]
    for i in range(len(pts)):
        cv2.line(frame, pts[i], pts[(i + 1) % len(pts)], color, 2)


def _draw_person(frame, signal, track_id, w, h, rule, fired_labels):
    x1, y1, x2, y2 = signal.person_bbox
    box_color = ALERT_BOX_COLOR if fired_labels else PERSON_BOX_COLOR
    thickness = 3 if fired_labels else 1
    cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, thickness)
    cv2.putText(frame, f"person_{track_id}", (x1, max(0, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 1)

    # Referência de ombro/quadril (mesma usada por HandDisappearanceRule
    # pra classificar região "incomum" vs "normal") — desenhada como uma
    # linha horizontal curta dentro da largura da pessoa, só pra ajudar a
    # enxergar visualmente onde a régua está sendo aplicada.
    if signal.shoulder_y_norm is not None:
        sy = int(signal.shoulder_y_norm * h)
        cv2.line(frame, (x1, sy), (x2, sy), SHOULDER_LINE_COLOR, 1)
    if signal.hip_y_norm is not None:
        hy = int(signal.hip_y_norm * h)
        cv2.line(frame, (x1, hy), (x2, hy), HIP_LINE_COLOR, 1)

    for hand_px, hand_norm in zip(signal.hands_px, signal.hands_norm):
        if hand_px is None:
            continue
        color = _in_zone_color(hand_norm, rule)
        cv2.circle(frame, hand_px, 6, color, -1)

    if fired_labels:
        label = " + ".join(fired_labels)
        cv2.putText(frame, label, (x1, min(h - 5, y2 + 18)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, ALERT_BOX_COLOR, 2)


def _draw_bags(frame, bags):
    """Desenha os recipientes detectados (mochila/bolsa/mala, ver
    BAG_CLASS_IDS em detector.py) -- só pra visualizar a extração nova,
    nenhuma regra usa isso ainda."""
    for bbox, score, label in bags:
        x1, y1, x2, y2 = bbox
        cv2.rectangle(frame, (x1, y1), (x2, y2), BAG_BOX_COLOR, 1)
        cv2.putText(
            frame, f"{label} {score:.2f}", (x1, max(0, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, BAG_BOX_COLOR, 1,
        )


def _bbox_center(bbox):
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _group_tracks_by_appearance(track_appearance, frame_size, max_gap_seconds, max_move_norm, max_color_distance):
    """Roda DEPOIS que o vídeo inteiro já foi processado -- por isso não
    dá pra viver dentro de tracker.py, que só enxerga um frame por vez.
    track_appearance: {track_id: {first_time_s, first_bbox, first_sig,
    last_time_s, last_bbox, last_sig}}, já preenchido pelo loop principal.

    Greedy, na ordem em que cada track COMEÇOU: pra cada track novo,
    procura entre os grupos já abertos (cada um representa uma pessoa
    provável) aquele cujo último track visto (a) TERMINOU antes desse aqui
    começar -- gap negativo = os dois coexistiram na cena, são pessoas
    diferentes na certa, geometria do IouTracker já garante isso -- (b)
    dentro da janela de tempo, (c) perto o bastante em posição, e (d) com
    assinatura de cor parecida; entre os candidatos, fica com o de menor
    distância de cor. Sem candidato -> abre um grupo novo (pode ser uma
    pessoa que só passou uma vez).

    Retorna (track_to_group: {track_id: group_id}, groups: lista de dicts
    com id/members/distances, na ordem em que foram abertos)."""
    w, h = frame_size
    diagonal = (w ** 2 + h ** 2) ** 0.5

    groups = []
    track_to_group = {}
    ordered = sorted(track_appearance.items(), key=lambda kv: kv[1]["first_time_s"])

    for track_id, rec in ordered:
        best = None
        for group in groups:
            gap = rec["first_time_s"] - group["last_time_s"]
            if gap < 0 or gap > max_gap_seconds:
                continue
            cx1, cy1 = _bbox_center(group["last_bbox"])
            cx2, cy2 = _bbox_center(rec["first_bbox"])
            move_norm = ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5 / diagonal if diagonal else 0.0
            if move_norm > max_move_norm:
                continue
            color_dist = signature_distance(group["last_sig"], rec["first_sig"])
            if color_dist > max_color_distance:
                continue
            if best is None or color_dist < best[1]:
                best = (group, color_dist)

        if best is not None:
            group, color_dist = best
            group["last_time_s"] = rec["last_time_s"]
            group["last_bbox"] = rec["last_bbox"]
            group["last_sig"] = rec["last_sig"]
            group["members"].append(track_id)
            group["distances"].append(color_dist)
            track_to_group[track_id] = group["id"]
        else:
            group_id = f"pessoa_{len(groups) + 1}"
            groups.append({
                "id": group_id,
                "last_time_s": rec["last_time_s"],
                "last_bbox": rec["last_bbox"],
                "last_sig": rec["last_sig"],
                "members": [track_id],
                "distances": [],
            })
            track_to_group[track_id] = group_id

    return track_to_group, groups


def main():
    args = parse_args()
    zone_points = [tuple(p) for p in json.loads(args.zone)]
    exclusion_zones = [[tuple(p) for p in zone] for zone in json.loads(args.exclusion_zone)]
    missing_frames_threshold = args.missing_frames_threshold or args.still_frames_threshold

    if not os.path.exists(args.video_path):
        raise SystemExit(f"Arquivo de vídeo não encontrado: {args.video_path}")

    cap = cv2.VideoCapture(args.video_path)
    if not cap.isOpened():
        raise SystemExit(f"Não foi possível abrir o vídeo: {args.video_path}")

    source_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    effective_fps = source_fps / args.frame_skip

    output_dir = args.output_dir or os.path.dirname(os.path.abspath(args.video_path))
    os.makedirs(output_dir, exist_ok=True)
    video_stem = os.path.splitext(os.path.basename(args.video_path))[0]
    log_path = os.path.join(output_dir, f"{video_stem}_eventos.csv")
    annotated_path = os.path.join(output_dir, f"{video_stem}_anotado.mp4")

    log.info(f"Vídeo: {args.video_path} ({frame_w}x{frame_h}, {source_fps:.1f}fps nativo, {total_frames} frames)")
    log.info(f"Backend de detecção: {DETECTION_BACKEND}")
    log.info(f"Zona: {zone_points}")
    if exclusion_zones:
        log.info(f"Zona(s) de exclusão: {exclusion_zones}")
    log.info(f"Threshold mão parada: {args.still_frames_threshold} frames | mão desaparecida: {missing_frames_threshold} frames")
    if args.frame_skip > 1:
        log.warning(
            f"frame-skip={args.frame_skip}: processando 1 a cada {args.frame_skip} frames — fps efetivo "
            f"{effective_fps:.2f} (vs {source_fps:.1f} nativo do vídeo). Os thresholds acima são contados em "
            f"FRAMES, então os números desta rodada não valem 1:1 pra calibração da câmera real nesse fps "
            f"diferente — só use os resultados pra observar comportamento, recalibre com --frame-skip 1 "
            f"(padrão) antes de decidir valores de verdade."
        )
    else:
        log.info("frame-skip=1 (nenhum frame pulado) — fps efetivo bate com o vídeo de origem, mesmo comportamento de frame-a-frame da box real.")

    perception = PerceptionPipeline(frame_size=(frame_w, frame_h), bag_confidence=args.bag_confidence)
    tracker = IouTracker()
    rule = SuspiciousBehaviorRule(
        zone_points=zone_points, still_frames_threshold=args.still_frames_threshold, exclusion_zones=exclusion_zones,
    )
    disappearance_rule = HandDisappearanceRule(
        zone_points=zone_points, missing_frames_threshold=missing_frames_threshold, exclusion_zones=exclusion_zones,
    )

    writer = None
    if not args.no_annotated_video:
        writer = cv2.VideoWriter(annotated_path, cv2.VideoWriter_fourcc(*"avc1"), effective_fps, (frame_w, frame_h))

    alert_client = None
    clip_recorder = None
    camera_label = args.camera_label or f"Teste offline — {video_stem}"
    pre_event_frame_count = max(1, int(args.pre_event_seconds * effective_fps))
    frame_buffer = collections.deque(maxlen=pre_event_frame_count)  # (timestamp, frame) — igual RollingCapture.buffer
    last_alert_video_time = {}  # person_id -> tempo de vídeo (segundos) do último envio, pro cooldown
    if args.send_to_backend:
        clips_dir = os.path.join(output_dir, "clips_teste_offline")
        clip_recorder = ClipRecorder(output_dir=clips_dir, fps_target=effective_fps)
        alert_client = AlertClient(api_base_url=args.api_base_url, api_key=args.api_key, store_id=args.store_id)
        log.info(
            f"Envio pro backend LIGADO — loja {args.store_id}, câmera_label='{camera_label}' "
            f"({args.api_base_url}). Só eventos com confiança >= {args.min_confidence} são enviados, "
            f"com cooldown de {COOLDOWN_SECONDS}s de tempo de vídeo por pessoa."
        )

    events = []
    highlight_hold_frames = max(1, int(HIGHLIGHT_HOLD_SECONDS * effective_fps))
    active_highlights = {}  # person_id -> frames restantes de destaque visual
    # track_id -> {first_time_s, first_bbox, first_sig, last_time_s, last_bbox,
    # last_sig} -- alimentado a cada frame, consumido só no fim (ver
    # _group_tracks_by_appearance) pro relatório de agrupamento por aparência.
    track_appearance = {}

    frame_index = 0
    processed_count = 0
    start_time = time.perf_counter()

    try:
        # utf-8-sig (BOM) + ";" como separador -- Excel em Windows pt-BR usa
        # "," como separador decimal, então trata "," na LISTA como parte do
        # número e não como delimitador: um CSV com "," abre inteiro numa
        # coluna só, sem dar erro nenhum (o arquivo está correto, o Excel
        # que interpreta errado por padrão nessa configuração regional).
        with open(log_path, "w", newline="", encoding="utf-8-sig") as log_file:
            csv_writer = csv.writer(log_file, delimiter=";")
            csv_writer.writerow([
                "frame", "tempo_video_s", "pessoa", "regra", "confianca", "teria_alertado", "enviado_backend", "motivo",
            ])

            while True:
                ok, frame = cap.read()
                if not ok:
                    break  # fim do arquivo — termina normalmente, sem tentar "reconectar"

                if frame_index % args.frame_skip != 0:
                    frame_index += 1
                    continue

                # Cópia ANTES de qualquer desenho de anotação — o bloco de
                # vídeo anotado mais abaixo desenha em cima de `frame` in-place
                # (cv2.rectangle/circle mutam o array); se guardássemos a
                # referência direta aqui, o clipe mandado pro backend sairia
                # com as anotações de debug desenhadas, não o vídeo original.
                frame_buffer.append((time.time(), frame.copy()))

                signals, bags = perception.process(frame)
                track_ids = tracker.update([s.person_bbox for s in signals], (frame_w, frame_h))

                for ended in tracker.ended_tracks:
                    ended_id = f"person_{ended.track_id}"
                    rule.forget(ended_id)
                    disappearance_rule.forget(ended_id)
                    active_highlights.pop(ended_id, None)

                video_time_s = frame_index / source_fps

                for track_id, signal in zip(track_ids, signals):
                    person_id = f"person_{track_id}"

                    if not args.no_appearance_grouping:
                        # Precisa ser ANTES do bloco de desenho lá embaixo --
                        # esse mesmo `frame` é reaproveitado ali e passa a
                        # ter as anotações de debug desenhadas em cima.
                        sig = color_signature(frame, signal.person_bbox)
                        if track_id not in track_appearance:
                            track_appearance[track_id] = {
                                "first_time_s": video_time_s, "first_bbox": signal.person_bbox, "first_sig": sig,
                                "last_time_s": video_time_s, "last_bbox": signal.person_bbox, "last_sig": sig,
                            }
                        else:
                            rec = track_appearance[track_id]
                            rec["last_time_s"] = video_time_s
                            rec["last_bbox"] = signal.person_bbox
                            rec["last_sig"] = sig

                    still_result = rule.evaluate(person_id, signal.hands_norm)
                    disappear_result = disappearance_rule.evaluate(person_id, signal, bags)
                    is_suspicious, confidence, reason = combine_rule_results(still_result, disappear_result)

                    fired_labels = []
                    if still_result[0]:
                        fired_labels.append("mao_parada")
                    if disappear_result[0]:
                        fired_labels.append("mao_desapareceu")

                    if fired_labels:
                        rule_label = "+".join(fired_labels)
                        would_alert = confidence >= args.min_confidence
                        active_highlights[person_id] = (highlight_hold_frames, rule_label)
                        log.info(
                            f"frame {frame_index} ({video_time_s:.1f}s) {person_id}: {rule_label} "
                            f"confiança={confidence:.2f} {'[ALERTARIA]' if would_alert else '[abaixo do threshold]'}"
                        )

                        sent_to_backend = False
                        if would_alert and alert_client is not None:
                            last_sent = last_alert_video_time.get(person_id)
                            in_cooldown = last_sent is not None and (video_time_s - last_sent) < COOLDOWN_SECONDS
                            if in_cooldown:
                                log.info(f"  -> em cooldown ({video_time_s - last_sent:.0f}s desde o último envio de {person_id}, esperando {COOLDOWN_SECONDS}s de vídeo)")
                            elif not frame_buffer:
                                log.warning("  -> buffer de pré-evento ainda vazio (disparou cedo demais no vídeo), não dá pra montar o clipe ainda")
                            else:
                                last_alert_video_time[person_id] = video_time_s
                                try:
                                    pre_frames = list(frame_buffer)
                                    thumbnail = clip_recorder.thumbnail_from_clip(pre_frames)
                                    adapter = _CaptureAdapter(cap, effective_fps)
                                    clip_path = clip_recorder.write_clip(pre_frames, adapter, args.post_event_seconds)
                                    # write_clip já corrige o índice do MP4 sozinho (ver clip_recorder._make_faststart)
                                    # o adaptador leu do MESMO cap que o loop
                                    # principal usa -- sem isso, frame_index (e
                                    # video_time_s, e o cooldown) ficam
                                    # dessincronizados da posição real do arquivo
                                    # a partir daqui.
                                    frame_index += adapter.frames_yielded
                                    alert_response = alert_client.send_alert(
                                        camera_id=args.camera_id,
                                        camera_label=camera_label,
                                        confidence=confidence,
                                        reason=reason,
                                        clip_path=clip_path,
                                        thumbnail_bytes=thumbnail,
                                    )
                                    # send_alert() engole RequestException internamente
                                    # e devolve None em vez de levantar (pensado pra
                                    # main.py, onde isso vira reenfileiramento futuro,
                                    # não deve derrubar a detecção ao vivo) -- aqui
                                    # precisa checar o retorno, senão uma falha de
                                    # rede real (timeout, DNS, etc.) passava batido
                                    # como sucesso só por não ter lançado exceção.
                                    if alert_response is None:
                                        raise RuntimeError("send_alert() retornou None (falha já logada por [AlertClient] acima)")
                                    sent_to_backend = True
                                    log.info(f"  -> alerta enviado pro backend (loja {args.store_id})")
                                except Exception as exc:
                                    log.warning(f"  -> falha ao enviar alerta pro backend, teste continua rodando: {exc}")

                        csv_writer.writerow([
                            frame_index, f"{video_time_s:.2f}", person_id, rule_label,
                            confidence, would_alert, sent_to_backend, reason,
                        ])
                        events.append((frame_index, person_id, rule_label, confidence, would_alert, sent_to_backend, track_id))

                if writer is not None:
                    _draw_zone(frame, zone_points, frame_w, frame_h)
                    for exclusion_points in exclusion_zones:
                        _draw_zone(frame, exclusion_points, frame_w, frame_h, color=EXCLUSION_ZONE_COLOR)
                    if not args.no_show_bags:
                        _draw_bags(frame, bags)
                    for track_id, signal in zip(track_ids, signals):
                        person_id = f"person_{track_id}"
                        hold, rule_label = active_highlights.get(person_id, (0, None))
                        _draw_person(
                            frame, signal, track_id, frame_w, frame_h, rule,
                            fired_labels=[rule_label] if hold > 0 else [],
                        )
                        if hold > 0:
                            active_highlights[person_id] = (hold - 1, rule_label)
                    writer.write(frame)

                processed_count += 1
                frame_index += 1

                if processed_count % 200 == 0:
                    elapsed = time.perf_counter() - start_time
                    log.info(f"... {processed_count} frames processados ({processed_count / elapsed:.1f} fps de processamento real)")
    finally:
        cap.release()
        if writer is not None:
            writer.release()
        perception.close()

    if writer is not None:
        log.info("Corrigindo o índice do vídeo anotado pra abrir em qualquer player (pode levar alguns segundos)...")
        _make_faststart(annotated_path)

    elapsed = time.perf_counter() - start_time
    processing_fps = processed_count / elapsed if elapsed > 0 else 0.0

    log.info("=" * 60)
    log.info(f"Concluído: {processed_count} frames processados em {elapsed:.1f}s ({processing_fps:.2f} fps de processamento real nesta máquina)")
    log.info(f"Eventos disparados: {len(events)} (dos quais {sum(1 for e in events if e[4])} teriam gerado alerta com min_confidence={args.min_confidence})")
    if alert_client is not None:
        log.info(f"Enviados de verdade pro backend: {sum(1 for e in events if e[5])} (o resto ficou em cooldown ou abaixo do threshold)")
    log.info(f"Log CSV: {log_path}")
    if writer is not None:
        log.info(f"Vídeo anotado: {annotated_path}")

    if not args.no_appearance_grouping and track_appearance:
        track_to_group, groups = _group_tracks_by_appearance(
            track_appearance, frame_size=(frame_w, frame_h),
            max_gap_seconds=args.appearance_max_gap_seconds,
            max_move_norm=args.appearance_max_move_norm,
            max_color_distance=args.appearance_max_color_distance,
        )
        for group in groups:
            members = group["members"]
            group["duration_s"] = (
                max(track_appearance[t]["last_time_s"] for t in members)
                - min(track_appearance[t]["first_time_s"] for t in members)
            )
        merged_groups = [g for g in groups if len(g["members"]) > 1]
        min_duration = args.appearance_min_duration_seconds
        likely_real = [g for g in groups if g["duration_s"] >= min_duration]

        log.info("=" * 60)
        log.info(
            f"Agrupamento por aparência (heurístico por cor de roupa -- NÃO alterou regras, cooldown "
            f"nem envio pro backend): {len(track_appearance)} track_id(s) do tracker consolidados em "
            f"{len(groups)} pessoa(s) provável(eis) no total."
        )
        if min_duration > 0:
            log.info(
                f"  Dessas, {len(likely_real)} aparecem por >= {min_duration:.1f}s -- estimativa mais "
                f"realista de pessoas de verdade (as outras {len(groups) - len(likely_real)} tendem a ser "
                f"ruído do detector/tracker: um frame isolado ou fragmento curto demais pra ser alguém "
                f"entrando e saindo de quadro de verdade). Ver coluna 'provavel_ruido' no CSV; ajuste "
                f"--appearance-min-duration-seconds se quiser outro corte."
            )
        if merged_groups:
            for group in merged_groups:
                log.info(f"  {group['id']}: track_ids {group['members']} (distância de cor média {sum(group['distances']) / len(group['distances']):.2f})")
        else:
            log.info("  Nenhuma fusão feita -- ou cada track_id já era uma pessoa distinta, ou nenhuma correspondência de cor ficou dentro dos limites configurados.")
        log.info(
            "  Heurístico: roupa parecida entre pessoas diferentes pode enganar. Confira o vídeo "
            "anotado antes de usar esse número pra decisão real; ajuste --appearance-max-* se sobrar "
            "ou faltar fusão."
        )

        agrupados_path = os.path.join(output_dir, f"{video_stem}_pessoas_agrupadas.csv")
        with open(agrupados_path, "w", newline="", encoding="utf-8-sig") as f:  # ver comentário no log_path acima
            csv_writer = csv.writer(f, delimiter=";")
            csv_writer.writerow([
                "pessoa_provavel", "track_ids", "primeiro_aparecimento_s", "ultimo_aparecimento_s",
                "duracao_s", "provavel_ruido", "eventos_disparados", "teria_alertado", "distancia_cor_media",
            ])
            for group in groups:
                members = set(group["members"])
                group_events = [e for e in events if e[6] in members]
                avg_dist = f"{sum(group['distances']) / len(group['distances']):.3f}" if group["distances"] else ""
                csv_writer.writerow([
                    group["id"],
                    ",".join(str(t) for t in group["members"]),
                    f"{min(track_appearance[t]['first_time_s'] for t in members):.2f}",
                    f"{max(track_appearance[t]['last_time_s'] for t in members):.2f}",
                    f"{group['duration_s']:.2f}",
                    min_duration > 0 and group["duration_s"] < min_duration,
                    len(group_events),
                    sum(1 for e in group_events if e[4]),
                    avg_dist,
                ])
        log.info(f"Relatório de pessoas agrupadas: {agrupados_path}")

    if args.frame_skip > 1:
        log.warning(
            f"Lembrete: essa rodada usou frame-skip={args.frame_skip} (fps efetivo {effective_fps:.2f}, "
            f"não o {source_fps:.1f} nativo do vídeo) — recalibre com --frame-skip 1 antes de levar os "
            f"valores pra configuração da câmera real."
        )


if __name__ == "__main__":
    main()
