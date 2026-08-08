import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
import datetime

from database import get_db
from models import Alert, AlertStatus, Camera, Store, User
from schemas import AlertOut, AlertReviewIn
from auth import get_current_user, get_store_from_edge_key, assert_user_can_access_store
from storage import ClipStorage
from tenant_context import set_company_context, set_store_lookup

router = APIRouter(prefix="/v1", tags=["alerts"])
clip_storage = ClipStorage()


# --- Recebido da BOX de detecção instalada na loja -------------------------

@router.post("/stores/{store_id}/alerts", response_model=AlertOut)
def receive_alert(
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

    clip_bytes = clip.file.read()
    clip_url = clip_storage.upload_clip(store_id, clip_bytes, clip.content_type)

    thumbnail_url = None
    if thumbnail is not None:
        thumb_bytes = thumbnail.file.read()
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
    db.add(alert)
    db.commit()
    # commit() encerra a transação e reseta o SET LOCAL setado pelo
    # get_store_from_edge_key — precisa religar antes do refresh() abaixo.
    set_store_lookup(db, store_id)
    db.refresh(alert)

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
