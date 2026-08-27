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
from config import _DEFAULT_ZONE, _DEFAULT_HAND_STILL_FRAMES, _DEFAULT_MIN_CONFIDENCE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("test_offline")

# Quantos frames o destaque visual de "regra disparou" fica marcado no
# vídeo anotado depois do frame que disparou — só pra dar tempo de ver
# ao pausar/avançar quadro a quadro, o disparo em si é instantâneo.
HIGHLIGHT_HOLD_SECONDS = 1.0

ZONE_COLOR = (0, 210, 255)       # amarelo (BGR) — contorno da zona de interesse
HAND_IN_ZONE_COLOR = (0, 220, 0)     # verde — mão visível dentro da zona
HAND_OUT_ZONE_COLOR = (160, 160, 160)  # cinza — mão visível fora da zona
SHOULDER_LINE_COLOR = (255, 200, 0)   # ciano — referência de ombro
HIP_LINE_COLOR = (200, 0, 200)        # magenta — referência de quadril
ALERT_BOX_COLOR = (0, 0, 255)         # vermelho — destaque quando uma regra dispara
PERSON_BOX_COLOR = (200, 200, 200)    # cinza claro — caixa da pessoa

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
        "--post-event-seconds", type=int, default=10,
        help="Quanto incluir DEPOIS do disparo no clipe (default: 10, igual ao padrão de StoreConfig).",
    )

    args = parser.parse_args()
    if args.send_to_backend and not (args.store_id and args.api_key):
        parser.error("--send-to-backend precisa de --store-id e --api-key")
    return args


def _in_zone_color(hand_pos, zone_rule):
    if hand_pos is None:
        return None
    return HAND_IN_ZONE_COLOR if zone_rule._in_zone(hand_pos) else HAND_OUT_ZONE_COLOR


def _draw_zone(frame, zone_points, w, h):
    if not zone_points:
        return
    pts = [(int(x * w), int(y * h)) for x, y in zone_points]
    for i in range(len(pts)):
        cv2.line(frame, pts[i], pts[(i + 1) % len(pts)], ZONE_COLOR, 2)


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


def main():
    args = parse_args()
    zone_points = [tuple(p) for p in json.loads(args.zone)]
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

    perception = PerceptionPipeline(frame_size=(frame_w, frame_h))
    tracker = IouTracker()
    rule = SuspiciousBehaviorRule(zone_points=zone_points, still_frames_threshold=args.still_frames_threshold)
    disappearance_rule = HandDisappearanceRule(zone_points=zone_points, missing_frames_threshold=missing_frames_threshold)

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

    frame_index = 0
    processed_count = 0
    start_time = time.perf_counter()

    try:
        with open(log_path, "w", newline="", encoding="utf-8") as log_file:
            csv_writer = csv.writer(log_file)
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

                signals = perception.process(frame)
                track_ids = tracker.update([s.person_bbox for s in signals], (frame_w, frame_h))

                for ended in tracker.ended_tracks:
                    ended_id = f"person_{ended.track_id}"
                    rule.forget(ended_id)
                    disappearance_rule.forget(ended_id)
                    active_highlights.pop(ended_id, None)

                video_time_s = frame_index / source_fps

                for track_id, signal in zip(track_ids, signals):
                    person_id = f"person_{track_id}"

                    still_result = rule.evaluate(person_id, signal.hands_norm)
                    disappear_result = disappearance_rule.evaluate(person_id, signal)
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
                                    alert_client.send_alert(
                                        camera_id=args.camera_id,
                                        camera_label=camera_label,
                                        confidence=confidence,
                                        reason=reason,
                                        clip_path=clip_path,
                                        thumbnail_bytes=thumbnail,
                                    )
                                    sent_to_backend = True
                                    log.info(f"  -> alerta enviado pro backend (loja {args.store_id})")
                                except Exception as exc:
                                    log.warning(f"  -> falha ao enviar alerta pro backend, teste continua rodando: {exc}")

                        csv_writer.writerow([
                            frame_index, f"{video_time_s:.2f}", person_id, rule_label,
                            confidence, would_alert, sent_to_backend, reason,
                        ])
                        events.append((frame_index, person_id, rule_label, confidence, would_alert, sent_to_backend))

                if writer is not None:
                    _draw_zone(frame, zone_points, frame_w, frame_h)
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
    if args.frame_skip > 1:
        log.warning(
            f"Lembrete: essa rodada usou frame-skip={args.frame_skip} (fps efetivo {effective_fps:.2f}, "
            f"não o {source_fps:.1f} nativo do vídeo) — recalibre com --frame-skip 1 antes de levar os "
            f"valores pra configuração da câmera real."
        )


if __name__ == "__main__":
    main()
