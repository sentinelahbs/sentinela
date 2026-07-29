import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import Store, User, UserRole
from schemas import StoreOut, StoreCreateIn, StoreCreateOut
from auth import get_current_user

router = APIRouter(prefix="/v1/stores", tags=["stores"])


@router.get("", response_model=list[StoreOut])
def list_my_stores(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Alimenta o seletor de lojas na sidebar do dashboard. OWNER vê todas
    as lojas da empresa; STORE_MANAGER só vê as lojas atribuídas a ele."""
    query = db.query(Store).filter(Store.company_id == user.company_id)
    if user.role == UserRole.STORE_MANAGER:
        assigned = (user.assigned_store_ids or "").split(",")
        query = query.filter(Store.id.in_(assigned))
    return query.all()


@router.post("", response_model=StoreCreateOut)
def create_store(
    payload: StoreCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Adiciona mais uma loja à empresa do usuário logado. Restrito a
    OWNER — um gestor de loja (STORE_MANAGER) não deveria conseguir criar
    novas lojas na conta, só revisar alertas das que já foram atribuídas
    a ele."""
    if user.role != UserRole.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas o dono da conta pode adicionar lojas")

    store = Store(
        company_id=user.company_id,
        name=payload.name,
        city=payload.city,
        edge_api_key=secrets.token_urlsafe(32),
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return store
