import logging
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
import datetime

from ai_review import analyze_alert
from database import SessionLocal, get_db
from models import Alert, AlertStatus, Camera, Company, Store, User
from schemas import AlertOut, AlertReviewIn
from auth import get_current_user, get_store_from_edge_key, assert_user_can_access_store
from storage import ClipStorage
from tenant_context import set_company_context, set_store_lookup

router = APIRouter(prefix="/v1", tags=["alerts"])
clip_storage = ClipStorage()
log = logging.getLogger("ai_review")


def _run_ai_review(alert_id: str, company_id: str, clip_bytes: bytes, reason: str) -> None:
    """Roda em background (ver BackgroundTasks.add_task abaixo) -- por
    rodar DEPOIS da resposta HTTP já ter sido enviada, a Session da
    requisição original já foi fechada (get_db fecha no finally), por
    isso abre uma Session própria aqui em vez de reaproveitar a `db` do
    request. Mesmo princípio de sempre: nunca deixa uma falha aqui virar
    exceção não tratada (rodando fora de um request, isso derrubaria o
    processo do worker, não só devolveria um 500)."""
    result = analyze_alert(clip_bytes, reason)
    if result is None:
        return
    veredito, justificativa = result

    db = SessionLocal()
    try:
        set_company_context(db, company_id)
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if alert is None:
            return
        alert.ai_verdict = veredito
        alert.ai_justification = justificativa
        db.commit()
    except Exception as exc:
        log.warning(f"[ai_review] Falha ao salvar parecer da IA no alerta {alert_id}: {exc}")
    finally:
        db.close()

# Limites de upload do clipe/thumbnail enviados pela box. Um clipe típico
# (5s de pré-evento + 10s de pós-evento, ver `pre_event_seconds` /
# `post_event_seconds` em edge-detection/config.py) gravado em H.264 fica
# na casa de poucos MB — 100 MB dá folga generosa até pra câmeras em
# resolução alta ou sem o codec H.264 disponível (fallback mp4v, maior).
# A thumbnail é um único frame JPEG, 10 MB já é folga enorme pra isso.
MAX_CLIP_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_THUMBNAIL_UPLOAD_BYTES = 10 * 1024 * 1024
_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024

# O content-type do clipe é gravado como ContentType do objeto no S3/R2
# (ver storage.py) e depois servido de volta via URL assinada — se
# aceitássemos qualquer valor que o cliente mandar, uma box comprometida
# (ou alguém que roubou a API key da loja) poderia declarar "text/html"
# num clipe malicioso e conseguir XSS armazenado em quem abrisse a URL
# direto no navegador. O alert_client.py real sempre manda "video/mp4" —
# aceitar qualquer "video/*" dá folga pra variações de box/câmera sem
# abrir a porta pra tipos perigosos.
_ALLOWED_CLIP_CONTENT_TYPES_PREFIX = "video/"


def _read_upload_limited(upload: UploadFile, max_bytes: int, field_name: str) -> bytes:
    """Lê um UploadFile em blocos, cortando assim que o total ultrapassa
    max_bytes. Não dá pra confiar no Content-Length declarado pelo cliente
    (quem chama esse endpoint é uma box autenticada só por API key, não um
    usuário logado) — por isso o corte é feito durante a leitura, e nunca
    é bufferizado mais que max_bytes (+ um bloco) na memória do processo,
    não importa o que o cliente diga que vai mandar."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = upload.file.read(_UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"Arquivo '{field_name}' excede o tamanho máximo permitido "
                f"({max_bytes // (1024 * 1024)} MB)",
            )
        chunks.append(chunk)
    return b"".join(chunks)


# --- Recebido da BOX de detecção instalada na loja -------------------------

@router.post("/stores/{store_id}/alerts", response_model=AlertOut)
def receive_alert(
    background_tasks: BackgroundTasks,
    store_id: str,
    camera_id: Optional[str] = Form(None),
    camera_label: str = Form(...),
    confidence: float = Form(...),
    reason: str = Form(...),
    clip: UploadFile = File(...),
    thumbnail: Optional[UploadFile] = File(None),
    store: Store = Depends(get_store_from_edge_key),
    db: Session = Depends(get_db),
):
    """Endpoint chamado pela box de cada loja (ver alert_client.py do
    módulo de detecção). Autenticado por API key da loja, não por login
    de usuário — quem chama aqui é um dispositivo, não uma pessoa."""

    # Empresa pausada pelo painel admin (ver routers/admin.py e
    # Company.access_paused) -- serviço de detecção fica inativo:
    # rejeita o alerta antes de gastar banda/processamento com o
    # upload do clipe. get_store_from_edge_key só libera RLS pra essa
    # linha específica de stores, não pra companies -- precisa religar
    # o contexto pra company_id da loja antes de conseguir ler isso.
    set_company_context(db, store.company_id)
    company = db.query(Company).filter(Company.id == store.company_id).first()
    if company is not None and company.access_paused:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Serviço de detecção pausado para esta empresa")

    # camera_id vem de fora (config da box) — nunca confia cru. Boxes
    # ainda não migradas mandam um placeholder de texto livre (ex:
    # "cam03", não um UUID) — validar o formato antes de consultar evita
    # que isso vire erro 500 (o driver do Postgres rejeita um valor não-
    # UUID ao comparar com a coluna). Se não corresponder a uma câmera
    # ativa cadastrada NESSA loja (formato inválido, box mal configurada,
    # câmera removida, id de outra loja etc.), grava o alerta do mesmo
    # jeito mas sem o vínculo, em vez de derrubar a inserção inteira.
    if camera_id is not None:
        try:
            uuid.UUID(camera_id)
        except ValueError:
            camera_id = None
        else:
            camera = db.query(Camera).filter(Camera.id == camera_id, Camera.store_id == store_id, Camera.active.is_(True)).first()
            if camera is None:
                camera_id = None

    if not (clip.content_type or "").startswith(_ALLOWED_CLIP_CONTENT_TYPES_PREFIX):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Tipo de arquivo '{clip.content_type}' não permitido para 'clip' (esperado video/*)",
        )

    clip_bytes = _read_upload_limited(clip, MAX_CLIP_UPLOAD_BYTES, "clip")
    clip_url = clip_storage.upload_clip(store_id, clip_bytes, clip.content_type)

    thumbnail_url = None
    if thumbnail is not None:
        thumb_bytes = _read_upload_limited(thumbnail, MAX_THUMBNAIL_UPLOAD_BYTES, "thumbnail")
        thumbnail_url = clip_storage.upload_thumbnail(store_id, thumb_bytes)

    alert = Alert(
        store_id=store_id,
        camera_id=camera_id,
        camera_label=camera_label,
        confidence=confidence,
        reason=reason,
        clip_url=clip_url,
        thumbnail_url=thumbnail_url,
        status=AlertStatus.PENDING,
    )
    # Valor puro antes do commit -- mesmo motivo de sempre (ver
    # review_alert logo abaixo): depois do commit() a sessão do request
    # perde o contexto de RLS, e o valor já está carregado no objeto.
    company_id = store.company_id

    db.add(alert)
    db.commit()
    # commit() encerra a transação e reseta o SET LOCAL setado pelo
    # get_store_from_edge_key — precisa religar antes do refresh() abaixo.
    set_store_lookup(db, store_id)
    db.refresh(alert)

    # Segundo parecer de IA (ver ai_review.py) -- roda em background,
    # depois que a resposta já foi mandada pra box, com sua própria
    # Session de banco (a `db` daqui fecha assim que a request termina).
    # Nunca atrasa nem derruba esse endpoint se falhar.
    background_tasks.add_task(_run_ai_review, alert.id, company_id, clip_bytes, reason)

    # Aqui é o ponto natural pra disparar push notification pro app mobile
    # do gestor responsável por essa loja, se a confiança for alta.

    return alert


# --- Consumido pelo dashboard web/mobile -----------------------------------

@router.get("/stores/{store_id}/alerts", response_model=list[AlertOut])
def list_alerts(
    store_id: str,
    status_filter: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    store = db.query(Store).filter(Store.id == store_id).first()
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loja não encontrada")
    assert_user_can_access_store(user, store)

    query = db.query(Alert).filter(Alert.store_id == store_id)
    if status_filter:
        query = query.filter(Alert.status == status_filter)
    return query.order_by(Alert.created_at.desc()).all()


@router.patch("/alerts/{alert_id}", response_model=AlertOut)
def review_alert(
    alert_id: str,
    payload: AlertReviewIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ação de revisão humana — 'confirmar ocorrência' ou 'marcar como
    falso positivo' no dashboard. Fica registrado quem revisou e quando,
    o que vira o log de auditoria mostrado na tela de detalhe do alerta."""
    if payload.status not in (AlertStatus.CONFIRMED.value, AlertStatus.DISMISSED.value):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Status inválido")

    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerta não encontrado")

    store = db.query(Store).filter(Store.id == alert.store_id).first()
    assert_user_can_access_store(user, store)

    # Valor puro antes do commit: depois dele o `user` (só lido, não
    # modificado) também expira, e reler user.company_id exigiria um
    # SELECT que o RLS ainda não liberou nesse instante.
    company_id = user.company_id

    alert.status = payload.status
    alert.reviewed_by_user_id = user.id
    alert.reviewed_at = datetime.datetime.utcnow()
    db.commit()
    # commit() encerra a transação e reseta o SET LOCAL setado pelo
    # get_current_user — precisa religar antes do refresh() abaixo.
    set_company_context(db, company_id)
    db.refresh(alert)
    return alert
