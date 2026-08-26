"""
Painel administrativo interno do VigIA — não é o dashboard que os
clientes (mercadinhos) usam. É onde VOCÊ, dono do VigIA, vê todas as
empresas cadastradas, quantas lojas cada uma tem, e o status de cobrança.

Protegido por get_current_admin (auth.py) — só usuários com
is_platform_admin=True acessam. Esse flag não tem endpoint de
auto-promoção de propósito: você liga ele direto no banco para sua
própria conta, a primeira vez.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Company, Store, User, Camera, Alert, TeamInvite, PasswordResetToken,
    CameraNeighbor, SuppressedEvent, PrepaidCheckout,
)
from schemas import (
    AdminCompanyOut, AdminCompanyDetailOut, AdminOnboardingOut, OnboardingStatusIn,
    AdminDeleteCompanyIn, CameraOut, CameraCalibrationUpdateIn,
)
from auth import get_current_admin, verify_password
from tenant_context import set_platform_admin_context
from storage import ClipStorage
from asaas_client import AsaasClient
from rate_limit import limiter

router = APIRouter(prefix="/v1/admin", tags=["admin"])
clip_storage = ClipStorage()
asaas = AsaasClient()

ONBOARDING_STATUSES = ("pending", "in_progress", "completed")


def _team_member_out(u: User):
    from schemas import TeamMemberOut
    store_ids = [s for s in (u.assigned_store_ids or "").split(",") if s]
    return TeamMemberOut(id=u.id, name=u.name, email=u.email, role=u.role.value, store_ids=store_ids)


@router.get("/companies", response_model=list[AdminCompanyOut])
def list_companies(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Alimenta a tabela principal do painel admin: todas as empresas
    clientes, com contagem de lojas/usuários e status de cobrança."""
    companies = db.query(Company).order_by(Company.created_at.desc()).all()

    result = []
    for company in companies:
        store_count = db.query(Store).filter(Store.company_id == company.id).count()
        user_count = db.query(User).filter(User.company_id == company.id).count()
        cameras_used = (
            db.query(Camera)
            .join(Store, Camera.store_id == Store.id)
            .filter(Store.company_id == company.id, Camera.active.is_(True))
            .count()
        )
        result.append(AdminCompanyOut(
            id=company.id,
            name=company.name,
            created_at=company.created_at.isoformat(),
            store_count=store_count,
            user_count=user_count,
            subscription_status=company.subscription_status,
            camera_limit=company.camera_limit or 0,
            cameras_used=cameras_used,
            access_paused=company.access_paused,
        ))
    return result


@router.get("/companies/{company_id}", response_model=AdminCompanyDetailOut)
def get_company_detail(
    company_id: str,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Detalhe de uma empresa específica — usado quando você clica numa
    linha da tabela no painel admin, para ver as lojas e a equipe dela."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada")

    stores = db.query(Store).filter(Store.company_id == company.id).all()
    users = db.query(User).filter(User.company_id == company.id).all()
    cameras_used = (
        db.query(Camera)
        .join(Store, Camera.store_id == Store.id)
        .filter(Store.company_id == company.id, Camera.active.is_(True))
        .count()
    )

    return AdminCompanyDetailOut(
        id=company.id,
        name=company.name,
        created_at=company.created_at.isoformat(),
        subscription_status=company.subscription_status,
        camera_limit=company.camera_limit or 0,
        cameras_used=cameras_used,
        access_paused=company.access_paused,
        stores=stores,
        users=[_team_member_out(u) for u in users],
    )


@router.get("/stores/{store_id}/cameras", response_model=list[CameraOut])
def list_store_cameras_admin(
    store_id: str,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Câmeras de uma loja (com o estado atual de calibração), pro admin
    ver/editar durante o piloto sem depender do dono da loja logar no
    dashboard. Usa o mesmo bypass de SELECT que list_companies já usa
    (cameras_admin_bypass, ver migração 2c999006f372)."""
    store = db.query(Store).filter(Store.id == store_id).first()
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loja não encontrada")
    return db.query(Camera).filter(Camera.store_id == store_id, Camera.active.is_(True)).all()


@router.patch("/cameras/{camera_id}/calibration", response_model=CameraOut)
def update_camera_calibration_admin(
    camera_id: str,
    payload: CameraCalibrationUpdateIn,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Mesma calibração remota que o dono edita no dashboard (ver
    update_camera_calibration em routers/cameras.py) — via painel admin,
    pra você (time VigIA) poder ajustar zona/threshold numa loja piloto
    remotamente, sem esperar o cliente mexer. Precisou de uma policy de
    UPDATE nova pro admin em `cameras` (cameras_admin_update, ver
    migração a3f7c9e21b4d) — só existia SELECT e DELETE até aqui."""
    camera = db.query(Camera).filter(Camera.id == camera_id, Camera.active.is_(True)).first()
    if camera is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Câmera não encontrada")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(camera, field, value)
    camera.calibration_updated_at = datetime.utcnow()

    db.commit()
    set_platform_admin_context(db)
    db.refresh(camera)
    return camera


@router.post("/companies/{company_id}/pause", response_model=AdminCompanyDetailOut)
def pause_company(
    company_id: str,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Suspende o SERVIÇO DE DETECÇÃO da empresa, não o login -- o
    dashboard continua acessível (o gestor precisa ver que está pausado),
    mas a box para de conseguir registrar alerta novo (receive_alert em
    routers/alerts.py rejeita com 403). Sem mexer em cobrança --
    subscription_status continua intocado, a assinatura no Asaas (se
    existir) segue cobrando normalmente. Ver Company.access_paused."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada")
    company.access_paused = True
    db.commit()
    set_platform_admin_context(db)
    return get_company_detail(company_id, admin, db)


@router.post("/companies/{company_id}/resume", response_model=AdminCompanyDetailOut)
def resume_company(
    company_id: str,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Reverte pause_company -- libera o acesso de volta."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada")
    company.access_paused = False
    db.commit()
    set_platform_admin_context(db)
    return get_company_detail(company_id, admin, db)


@router.delete("/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
def delete_company(
    request: Request,
    company_id: str,
    payload: AdminDeleteCompanyIn,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Exclusão REAL e irreversível de uma empresa -- apaga empresa,
    lojas, câmeras, usuários, alertas (e os clipes/thumbnails no R2 de
    cada loja) e cancela a assinatura no Asaas se existir. Não tem
    desfazer -- a confirmação por nome da empresa é feita no front, mas
    a ação só executa se a SENHA DO PRÓPRIO ADMIN logado bater (re-
    autenticação pra uma ação irreversível, não basta só ter a sessão
    ativa). Rate limit aqui é defesa extra contra uma sessão de admin
    roubada tentando forçar a senha por tentativa e erro.

    Ordem importa: sem ON DELETE CASCADE configurado no banco (ver
    migrations/), cada tabela filha precisa ser esvaziada antes da
    tabela que ela referencia via FK, senão a query de delete falha
    com violação de integridade referencial."""
    if not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Senha incorreta")

    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada")

    stores = db.query(Store).filter(Store.company_id == company_id).all()
    store_ids = [s.id for s in stores]
    camera_ids = [c.id for c in db.query(Camera).filter(Camera.store_id.in_(store_ids)).all()] if store_ids else []
    user_ids = [u.id for u in db.query(User).filter(User.company_id == company_id).all()]

    if store_ids:
        db.query(Alert).filter(Alert.store_id.in_(store_ids)).delete(synchronize_session=False)
        db.query(SuppressedEvent).filter(SuppressedEvent.store_id.in_(store_ids)).delete(synchronize_session=False)
    if camera_ids:
        db.query(CameraNeighbor).filter(
            CameraNeighbor.camera_id_a.in_(camera_ids) | CameraNeighbor.camera_id_b.in_(camera_ids)
        ).delete(synchronize_session=False)
        db.query(Camera).filter(Camera.id.in_(camera_ids)).delete(synchronize_session=False)
    db.query(TeamInvite).filter(TeamInvite.company_id == company_id).delete(synchronize_session=False)
    # PrepaidCheckout.claimed_company_id referencia companies.id (FK) --
    # sem apagar/desvincular essas linhas, o DELETE final na company
    # falha com violação de integridade referencial se essa empresa
    # tiver vindo do fluxo de aquisição por link (ver routers/auth.py).
    db.query(PrepaidCheckout).filter(PrepaidCheckout.claimed_company_id == company_id).delete(synchronize_session=False)
    if user_ids:
        db.query(PasswordResetToken).filter(PasswordResetToken.user_id.in_(user_ids)).delete(synchronize_session=False)
    if store_ids:
        db.query(Store).filter(Store.id.in_(store_ids)).delete(synchronize_session=False)
    db.query(User).filter(User.company_id == company_id).delete(synchronize_session=False)

    asaas_subscription_id = company.asaas_subscription_id
    db.query(Company).filter(Company.id == company_id).delete(synchronize_session=False)
    db.commit()

    # Fora da transação do banco de propósito: se a chamada ao Asaas
    # falhar, os dados já foram apagados (o que a exclusão promete) --
    # não faz sentido reverter isso por causa de uma API externa fora
    # do nosso controle. Loga em vez de derrubar a resposta.
    if asaas_subscription_id:
        try:
            asaas.cancel_subscription(asaas_subscription_id)
        except Exception as exc:
            print(f"[admin] Falha ao cancelar assinatura Asaas {asaas_subscription_id} (empresa {company_id} já excluída): {exc}")

    for store_id in store_ids:
        try:
            clip_storage.delete_store_clips(store_id)
        except Exception as exc:
            print(f"[admin] Falha ao apagar clipes da loja {store_id} (empresa {company_id} já excluída): {exc}")


def _onboarding_out(store: Store, company: Company) -> AdminOnboardingOut:
    return AdminOnboardingOut(
        store_id=store.id,
        store_name=store.name,
        company_id=company.id,
        company_name=company.name,
        payment_confirmed_at=company.payment_confirmed_at.isoformat() if company.payment_confirmed_at else None,
        onboarding_status=store.onboarding_status,
        online=store.online,
        last_seen_at=store.last_seen_at.isoformat() if store.last_seen_at else None,
    )


@router.get("/onboarding", response_model=list[AdminOnboardingOut])
def list_onboarding(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Fila de lojas aguardando conexão de câmeras — só empresas com
    pagamento já confirmado, da que está esperando há mais tempo pra
    mais recente (mesma lógica de fila de qualquer painel de suporte)."""
    rows = (
        db.query(Store, Company)
        .join(Company, Store.company_id == Company.id)
        .filter(Company.payment_confirmed_at.isnot(None))
        .filter(Store.onboarding_status != "completed")
        .order_by(Company.payment_confirmed_at.asc())
        .all()
    )
    return [_onboarding_out(store, company) for store, company in rows]


@router.patch("/stores/{store_id}/onboarding", response_model=AdminOnboardingOut)
def update_onboarding_status(
    store_id: str,
    payload: OnboardingStatusIn,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Botão de avançar/corrigir status na tela de onboarding do admin.
    "completed" só chega aqui por ação manual — nunca automático (ver
    stores.py store_heartbeat), já que câmera online não garante que o
    setup foi validado de verdade (ângulo certo, zona configurada etc.)."""
    if payload.status not in ONBOARDING_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Status inválido")

    store = db.query(Store).filter(Store.id == store_id).first()
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loja não encontrada")

    company = db.query(Company).filter(Company.id == store.company_id).first()
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada")

    # Valores puros: depois do commit() a instância expira, e reler os
    # atributos exigiria um SELECT sob o contexto de admin religado logo
    # abaixo — mais simples guardar antes.
    company_id = company.id
    company_name = company.name
    payment_confirmed_at = company.payment_confirmed_at

    store.onboarding_status = payload.status
    db.commit()
    # commit() encerra a transação e reseta o SET LOCAL setado por
    # get_current_admin — precisa religar antes do refresh() abaixo.
    set_platform_admin_context(db)
    db.refresh(store)

    return AdminOnboardingOut(
        store_id=store.id,
        store_name=store.name,
        company_id=company_id,
        company_name=company_name,
        payment_confirmed_at=payment_confirmed_at.isoformat() if payment_confirmed_at else None,
        onboarding_status=store.onboarding_status,
        online=store.online,
        last_seen_at=store.last_seen_at.isoformat() if store.last_seen_at else None,
    )
