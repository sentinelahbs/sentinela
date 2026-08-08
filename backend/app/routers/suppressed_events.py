"""
Log de auditoria das supressões de alerta feitas pelo correlator local da
box (ver correlator.py no módulo de detecção) — quando uma câmera decide
não reenviar um alerta por considerar continuação de um evento recente
numa câmera vizinha, fica registrado aqui pra o dono conseguir auditar
depois se a supressão fez sentido.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import Camera, Store, SuppressedEvent, User
from schemas import SuppressedEventIn, SuppressedEventOut
from auth import get_current_user, get_store_from_edge_key, assert_user_can_access_store

router = APIRouter(prefix="/v1/stores/{store_id}/suppressed-events", tags=["suppressed-events"])


@router.post("", status_code=status.HTTP_201_CREATED)
def report_suppressed_event(
    store_id: str,
    payload: SuppressedEventIn,
    store: Store = Depends(get_store_from_edge_key),
    db: Session = Depends(get_db),
):
    """Chamado pela box (ver correlator.py/alert_client.py do módulo de
    detecção) quando uma supressão acontece. Não é caminho crítico — se
    as duas câmeras informadas não baterem com a loja, só recusa; a box
    trata isso como não-fatal (ver AlertClient.report_suppressed_event)."""
    camera = db.query(Camera).filter(Camera.id == payload.camera_id, Camera.store_id == store_id).first()
    matched_camera = db.query(Camera).filter(Camera.id == payload.matched_camera_id, Camera.store_id == store_id).first()
    if camera is None or matched_camera is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Câmera não encontrada nesta loja")

    event = SuppressedEvent(
        store_id=store_id,
        camera_id=payload.camera_id,
        matched_camera_id=payload.matched_camera_id,
        track_id=payload.track_id,
        confidence=payload.confidence,
        appearance_distance=payload.appearance_distance,
    )
    db.add(event)
    db.commit()
    return {"received": True}


@router.get("", response_model=list[SuppressedEventOut])
def list_suppressed_events(
    store_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    store = db.query(Store).filter(Store.id == store_id).first()
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loja não encontrada")
    assert_user_can_access_store(user, store)

    events = (
        db.query(SuppressedEvent)
        .filter(SuppressedEvent.store_id == store_id)
        .order_by(SuppressedEvent.created_at.desc())
        .limit(200)
        .all()
    )
    if not events:
        return []

    camera_ids = {e.camera_id for e in events} | {e.matched_camera_id for e in events}
    labels = {c.id: c.label for c in db.query(Camera).filter(Camera.id.in_(camera_ids)).all()}

    return [
        SuppressedEventOut(
            id=e.id,
            camera_id=e.camera_id,
            camera_label=labels.get(e.camera_id, "?"),
            matched_camera_id=e.matched_camera_id,
            matched_camera_label=labels.get(e.matched_camera_id, "?"),
            track_id=e.track_id,
            confidence=e.confidence,
            appearance_distance=e.appearance_distance,
            created_at=e.created_at,
        )
        for e in events
    ]
