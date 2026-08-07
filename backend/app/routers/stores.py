import datetime
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import Store, User, UserRole
from schemas import StoreOut, StoreCreateIn, StoreCreateOut
from auth import get_current_user, get_store_from_edge_key
from tenant_context import set_company_context

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

    # Guarda como valor puro antes do commit: depois dele o SQLAlchemy
    # expira os atributos de TODOS os objetos da sessão (inclusive o
    # `user`, que só foi lido, não modificado) — reler user.company_id
    # nesse ponto exigiria um SELECT que o RLS ainda não liberou.
    company_id = user.company_id

    store = Store(
        company_id=company_id,
        name=payload.name,
        city=payload.city,
        edge_api_key=secrets.token_urlsafe(32),
    )
    db.add(store)
    db.commit()
    # commit() encerra a transação e reseta o SET LOCAL setado pelo
    # get_current_user — precisa religar antes do refresh() abaixo.
    set_company_context(db, company_id)
    db.refresh(store)
    return store


# --- Recebido da BOX de detecção instalada na loja -------------------------

@router.post("/{store_id}/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def store_heartbeat(store: Store = Depends(get_store_from_edge_key), db: Session = Depends(get_db)):
    """Ping periódico da box (ver heartbeat_sender no módulo de detecção) —
    é assim que o backend sabe se ela está online. "Offline" não é uma
    flag guardada; é derivado de last_seen_at na leitura (ver
    list_my_stores abaixo e routers/admin.py)."""
    store.last_seen_at = datetime.datetime.utcnow()
    # Primeiro heartbeat depois do pagamento confirmado já avança o
    # onboarding sozinho — "concluído" continua manual, só pelo admin
    # (câmera online não garante que o setup foi validado de verdade).
    if store.onboarding_status == "pending":
        store.onboarding_status = "in_progress"
    db.commit()
