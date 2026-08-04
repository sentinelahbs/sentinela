"""
Cadastro de câmeras por loja — com limite baseado em quantos pacotes de
5 câmeras a empresa contratou (camera_limit em Company).

Antes desse router, câmeras eram só um texto livre (camera_label) dentro
do alerta — não existia cadastro nem controle de quantidade. Agora o
cadastro é explícito e checado contra o limite contratado.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import Camera, Store, Company, User, UserRole
from schemas import CameraOut, CameraCreateIn
from auth import get_current_user, assert_user_can_access_store
from tenant_context import set_company_context

router = APIRouter(prefix="/v1/stores/{store_id}/cameras", tags=["cameras"])


def _company_camera_count(db: Session, company_id: str) -> int:
    """Conta câmeras ATIVAS em todas as lojas da empresa — o limite é
    por empresa (soma de todas as lojas), não por loja individual."""
    return (
        db.query(Camera)
        .join(Store, Camera.store_id == Store.id)
        .filter(Store.company_id == company_id, Camera.active.is_(True))
        .count()
    )


@router.get("", response_model=list[CameraOut])
def list_cameras(
    store_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    store = db.query(Store).filter(Store.id == store_id).first()
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loja não encontrada")
    assert_user_can_access_store(user, store)

    return db.query(Camera).filter(Camera.store_id == store_id, Camera.active.is_(True)).all()


@router.post("", response_model=CameraOut)
def create_camera(
    store_id: str,
    payload: CameraCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != UserRole.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas o dono da conta pode cadastrar câmeras")

    store = db.query(Store).filter(Store.id == store_id).first()
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loja não encontrada")
    assert_user_can_access_store(user, store)

    company = db.query(Company).filter(Company.id == store.company_id).first()
    current_count = _company_camera_count(db, company.id)

    if current_count >= company.camera_limit:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Limite de câmeras contratado atingido ({company.camera_limit}). "
            f"Contrate mais um pacote de 5 câmeras para adicionar novas câmeras.",
        )

    # Valor puro antes do commit: depois dele o SQLAlchemy expira os
    # atributos de todos os objetos da sessão (inclusive `company`, só
    # lido) — reler company.id nesse ponto exigiria um SELECT que o RLS
    # ainda não liberaria (ver tenant_context.py).
    company_id = company.id

    camera = Camera(store_id=store_id, label=payload.label, active=True)
    db.add(camera)
    db.commit()
    # commit() encerra a transação e reseta o SET LOCAL setado pelo
    # get_current_user — precisa religar antes do refresh() abaixo.
    set_company_context(db, company_id)
    db.refresh(camera)
    return camera


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_camera(
    store_id: str,
    camera_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != UserRole.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas o dono da conta pode remover câmeras")

    store = db.query(Store).filter(Store.id == store_id).first()
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loja não encontrada")
    assert_user_can_access_store(user, store)

    camera = db.query(Camera).filter(Camera.id == camera_id, Camera.store_id == store_id).first()
    if camera is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Câmera não encontrada")

    # Desativa em vez de apagar — mantém o histórico de alertas antigos
    # dessa câmera íntegro (Alert.camera_id referencia esse registro).
    camera.active = False
    db.commit()
