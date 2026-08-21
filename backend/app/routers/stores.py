import datetime
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import Store, User, UserRole
from schemas import StoreOut, StoreCreateIn, StoreCreateOut, EdgeWhoamiOut
from auth import get_current_user, get_store_from_edge_key, hash_edge_api_key
from tenant_context import set_company_context, set_edge_api_key_lookup

router = APIRouter(prefix="/v1/stores", tags=["stores"])
# Rotas que a BOX chama sem ainda saber o store_id (só tem a chave) —
# path separado de /v1/stores/{store_id}/... porque store_id ainda não
# existe nesse momento (ver set_edge_api_key_lookup).
edge_router = APIRouter(prefix="/v1/edge", tags=["edge"])


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

    # Texto puro só existe aqui, local, pra devolver na resposta desta
    # chamada — nunca é persistido (ver Store.edge_api_key_hash).
    plaintext_key = secrets.token_urlsafe(32)
    store = Store(
        company_id=company_id,
        name=payload.name,
        city=payload.city,
        edge_api_key_hash=hash_edge_api_key(plaintext_key),
    )
    db.add(store)
    db.commit()
    # commit() encerra a transação e reseta o SET LOCAL setado pelo
    # get_current_user — precisa religar antes do refresh() abaixo.
    set_company_context(db, company_id)
    db.refresh(store)
    return StoreCreateOut(id=store.id, name=store.name, city=store.city, edge_api_key=plaintext_key)


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


@edge_router.get("/whoami", response_model=EdgeWhoamiOut)
def edge_whoami(
    x_api_key: str = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    """Usado pelo assistente de configuração da box (roda no PC do
    cliente) — resolve o store_id a partir só da chave da loja, pra quem
    está instalando não precisar digitar/colar os dois valores (o
    dashboard nunca mostrou o store_id como algo copiável, só a chave)."""
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-API-Key ausente")

    key_hash = hash_edge_api_key(x_api_key)
    set_edge_api_key_lookup(db, key_hash)
    store = db.query(Store).filter(Store.edge_api_key_hash == key_hash).first()
    if store is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chave inválida")

    return EdgeWhoamiOut(store_id=store.id, store_name=store.name)
