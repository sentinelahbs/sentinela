"""
Cobrança da assinatura mensal via Pix (Asaas) — em pacotes de câmeras.

Modelo de preço: cada pacote libera 9 câmeras por R$ 649,90/mês. A
empresa escolhe quantos pacotes quer (camera_packages).

Duas situações distintas, tratadas de forma diferente:
  - PRIMEIRA compra: cria uma assinatura recorrente nova no Asaas.
  - Empresa JÁ tem assinatura ativa e está comprando pacotes
    ADICIONAIS: em vez de criar uma segunda assinatura solta (o que
    geraria duas cobranças Pix separadas todo mês), atualizamos o VALOR
    da assinatura existente para refletir o novo total, e cobramos uma
    cobrança avulsa (não recorrente) só da diferença, para começar a
    valer imediatamente em vez de esperar o próximo ciclo.

O camera_limit só é efetivamente aumentado quando o Asaas confirma o
pagamento via webhook (não no momento do /subscribe) — isso evita
liberar câmeras para uma cobrança que ainda não caiu.

Nota sobre RLS: depois de um db.commit(), o SQLAlchemy expira os
atributos de todos os objetos da sessão, e o SET LOCAL que libera o
RLS também é resetado pelo commit — por isso os valores de `company`
usados depois de qualquer commit() abaixo vêm de variáveis capturadas
antes, e cada commit seguido de mais alguma operação no banco religa o
contexto com set_company_context.
"""

import datetime
import os
import secrets
import time

import requests
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from models import User, Company, Camera, Store, UserRole, PrepaidCheckout, PendingStorePurchase
from schemas import (
    SubscribeIn, SubscribeOut, BillingStatusOut,
    PrepaidPixIn, PrepaidPixOut, PrepaidPixStatusOut,
    StorePurchaseIn, StorePurchaseOut, StorePurchaseStatusOut, StoreCreateOut,
)
from auth import get_current_user, hash_edge_api_key
from asaas_client import AsaasClient
from rate_limit import limiter, get_client_ip
from tenant_context import (
    set_company_context, set_billing_lookup, set_customer_lookup,
    set_prepaid_checkout_token_lookup, set_prepaid_checkout_id_lookup,
    set_prepaid_payment_id_lookup, set_store_purchase_payment_lookup,
)

router = APIRouter(prefix="/v1/billing", tags=["billing"])
asaas = AsaasClient()

# Preço por pacote de câmeras — mude aqui se o valor ou o tamanho do
# pacote mudar. É a fonte de verdade usada na cobrança em si (Asaas) e
# nas descrições de pagamento geradas pelo backend, MAS o dashboard
# (dashboard/src/App.jsx, mesmo nome de constante) tem sua própria
# cópia hardcoded pra exibição — não é buscada por API, então precisa
# ser atualizada junto sempre que estes dois valores mudarem aqui.
CAMERAS_PER_PACKAGE = 9
PRICE_PER_PACKAGE = 649.90

# Token que você define no painel do Asaas (Configurações -> Webhooks)
# e o Asaas envia de volta em todo webhook, para provarmos que a
# requisição realmente veio de lá, não de qualquer um na internet.
ASAAS_WEBHOOK_TOKEN = os.environ.get("ASAAS_WEBHOOK_TOKEN", "")

# URL do dashboard web publicado — usada pra montar o successUrl/cancelUrl
# do Checkout do Asaas (fluxo de aquisição por link, ver prepaid_checkout
# abaixo). Mesma variável já usada em email_client.py.
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5173")

PREPAID_CHECKOUT_EXPIRY_MINUTES = 60


def _company_camera_count(db: Session, company_id: str) -> int:
    return (
        db.query(Camera)
        .join(Store, Camera.store_id == Store.id)
        .filter(Store.company_id == company_id, Camera.active.is_(True))
        .count()
    )


def _get_pix_qr_code_or_none(payment_id: str) -> "dict | None":
    """O QR Code Pix às vezes ainda não está pronto no Asaas no instante
    em que a cobrança acaba de ser criada (confirmado em teste local
    contra o sandbox: a mesma chamada falhava com 400 na hora e
    funcionava segundos depois). Tenta algumas vezes antes de desistir —
    se mesmo assim não vier, o /subscribe retorna sem QR Code em vez de
    quebrar com 500, e o dashboard pode buscar de novo via /status."""
    for attempt in range(3):
        try:
            return asaas.get_pix_qr_code(payment_id)
        except requests.exceptions.HTTPError:
            if attempt < 2:
                time.sleep(1.5)
    return None


@router.post("/subscribe", response_model=SubscribeOut)
def subscribe(
    payload: SubscribeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != UserRole.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas o dono da conta pode assinar/ampliar o plano")

    if payload.camera_packages < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escolha ao menos 1 pacote de câmeras")

    company = db.query(Company).filter(Company.id == user.company_id).first()
    # Valores puros antes de qualquer commit: depois dele o SQLAlchemy
    # expira os atributos de `company` (só lido, não impede a expiração),
    # e reler um atributo do ORM nesse ponto exigiria um SELECT que o
    # RLS ainda não liberaria (ver nota no topo do arquivo).
    company_id = company.id
    company_name = company.name
    asaas_customer_id = company.asaas_customer_id
    asaas_subscription_id = company.asaas_subscription_id
    subscription_status = company.subscription_status
    camera_limit = company.camera_limit or 0
    current_pending = company.pending_camera_packages or 0

    camera_limit_pending = payload.camera_packages * CAMERAS_PER_PACKAGE

    # cria o cliente no Asaas só na primeira vez — tanto assinatura nova
    # quanto compra de pacote adicional reaproveitam o mesmo customer_id
    if not asaas_customer_id:
        customer = asaas.create_customer(
            name=company_name,
            email=user.email,
            cpf_cnpj=payload.cpf_cnpj,
            external_reference=company_id,
        )
        asaas_customer_id = customer["id"]
        company.asaas_customer_id = asaas_customer_id
        db.commit()
        set_company_context(db, company_id)

    company.pending_camera_packages = current_pending + payload.camera_packages
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

    has_active_subscription = bool(asaas_subscription_id) and subscription_status in ("active", "pending")

    if has_active_subscription:
        # EMPRESA JÁ TEM ASSINATURA: atualiza o valor recorrente para o
        # novo total, e cobra AGORA só a diferença via pagamento avulso
        current_packages = camera_limit // CAMERAS_PER_PACKAGE
        new_total_packages = current_packages + payload.camera_packages
        new_monthly_value = new_total_packages * PRICE_PER_PACKAGE
        incremental_value = payload.camera_packages * PRICE_PER_PACKAGE

        asaas.update_subscription(
            subscription_id=asaas_subscription_id,
            value=new_monthly_value,
            description=(
                f"VigIA — {new_total_packages} pacote(s) de {CAMERAS_PER_PACKAGE} câmeras "
                f"({new_total_packages * CAMERAS_PER_PACKAGE} câmeras) — {company_name}"
            ),
        )
        payment = asaas.create_payment(
            customer_id=asaas_customer_id,
            value=incremental_value,
            description=(
                f"VigIA — upgrade de +{payload.camera_packages} pacote(s) "
                f"({camera_limit_pending} câmeras adicionais) — {company_name}"
            ),
            due_date=tomorrow,
        )
        db.commit()

        qr = _get_pix_qr_code_or_none(payment["id"])
        return SubscribeOut(
            subscription_status=subscription_status,
            camera_limit_pending=camera_limit_pending,
            monthly_value=incremental_value,
            pix_qr_code_image=qr.get("encodedImage") if qr else None,
            pix_copy_paste=qr.get("payload") if qr else None,
            pix_expiration=qr.get("expirationDate") if qr else None,
        )

    # PRIMEIRA ASSINATURA da empresa
    monthly_value = payload.camera_packages * PRICE_PER_PACKAGE
    subscription = asaas.create_subscription(
        customer_id=asaas_customer_id,
        value=monthly_value,
        description=(
            f"VigIA — {payload.camera_packages} pacote(s) de {CAMERAS_PER_PACKAGE} câmeras "
            f"({camera_limit_pending} câmeras) — {company_name}"
        ),
        next_due_date=tomorrow,
    )
    company.asaas_subscription_id = subscription["id"]
    company.subscription_status = "pending"
    db.commit()

    # a primeira cobrança já nasce junto com a assinatura — buscamos ela
    # para conseguir mostrar o QR Code Pix na hora, sem o cliente esperar
    payments = asaas.get_payments_for_subscription(subscription["id"])
    if not payments:
        # a cobrança pode levar alguns segundos para aparecer do lado do
        # Asaas — o dashboard pode tentar de novo em caso de lista vazia
        return SubscribeOut(
            subscription_status="pending",
            camera_limit_pending=camera_limit_pending,
            monthly_value=monthly_value,
        )

    first_payment_id = payments[0]["id"]
    qr = _get_pix_qr_code_or_none(first_payment_id)

    return SubscribeOut(
        subscription_status="pending",
        camera_limit_pending=camera_limit_pending,
        monthly_value=monthly_value,
        pix_qr_code_image=qr.get("encodedImage") if qr else None,
        pix_copy_paste=qr.get("payload") if qr else None,
        pix_expiration=qr.get("expirationDate") if qr else None,
    )


@router.get("/status", response_model=BillingStatusOut)
def billing_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == user.company_id).first()
    cameras_used = _company_camera_count(db, company.id)
    return BillingStatusOut(
        subscription_status=company.subscription_status,
        camera_limit=company.camera_limit or 0,
        cameras_used=cameras_used,
    )


# --- Loja adicional (empresa JÁ existente comprando mais uma loja) -------
#
# Cada loja além da primeira custa PRICE_PER_PACKAGE (mesmo valor de um
# pacote de câmera, sem relação nenhuma com limite de câmera) — a Store
# de verdade e a edge_api_key só nascem depois que o Asaas confirma o
# pagamento (webhook), nunca no momento desta chamada. Ver
# PendingStorePurchase em models.py.

@router.post("/store-purchase", response_model=StorePurchaseOut)
def purchase_store(
    payload: StorePurchaseIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != UserRole.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas o dono da conta pode adicionar lojas")

    company = db.query(Company).filter(Company.id == user.company_id).first()
    company_id = company.id
    company_name = company.name
    asaas_customer_id = company.asaas_customer_id

    if not asaas_customer_id:
        if not payload.cpf_cnpj:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Informe o CPF/CNPJ do responsável para gerar a primeira cobrança desta empresa.",
            )
        customer = asaas.create_customer(
            name=company_name, email=user.email, cpf_cnpj=payload.cpf_cnpj, external_reference=company_id,
        )
        asaas_customer_id = customer["id"]
        company.asaas_customer_id = asaas_customer_id
        db.commit()
        set_company_context(db, company_id)

    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    payment = asaas.create_payment(
        customer_id=asaas_customer_id,
        value=PRICE_PER_PACKAGE,
        description=f"VigIA — loja adicional ({payload.name}) — {company_name}",
        due_date=tomorrow,
    )

    pending = PendingStorePurchase(
        company_id=company_id, name=payload.name, city=payload.city,
        asaas_payment_id=payment["id"], status="pending",
    )
    db.add(pending)
    db.commit()
    set_company_context(db, company_id)
    db.refresh(pending)

    qr = _get_pix_qr_code_or_none(payment["id"])
    return StorePurchaseOut(
        id=pending.id,
        monthly_value=PRICE_PER_PACKAGE,
        pix_qr_code_image=qr.get("encodedImage") if qr else None,
        pix_copy_paste=qr.get("payload") if qr else None,
        pix_expiration=qr.get("expirationDate") if qr else None,
    )


@router.get("/store-purchase/{purchase_id}/status", response_model=StorePurchaseStatusOut)
def store_purchase_status(
    purchase_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Valor puro capturado antes de qualquer commit -- depois de um
    # commit() o SQLAlchemy expira os atributos de TODOS os objetos da
    # sessão (inclusive `user`), e o SET LOCAL que libera o RLS também é
    # resetado; reler user.company_id nesse ponto exigiria uma consulta
    # que o RLS ainda não liberaria.
    company_id = user.company_id

    pending = db.query(PendingStorePurchase).filter(
        PendingStorePurchase.id == purchase_id, PendingStorePurchase.company_id == company_id,
    ).first()
    if pending is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compra não encontrada")

    if pending.status != "paid":
        return StorePurchaseStatusOut(status=pending.status)

    # Primeira consulta depois de "paid": cria a Store de verdade agora
    # (não no webhook) — só existe uma sessão autenticada do dono nesse
    # momento pra receber a edge_api_key em texto puro com segurança, e
    # ela só é mostrada esta única vez (mesmo princípio de create_store).
    pending_name = pending.name
    pending_city = pending.city

    plaintext_key = secrets.token_urlsafe(32)
    store = Store(
        company_id=company_id, name=pending_name, city=pending_city,
        edge_api_key_hash=hash_edge_api_key(plaintext_key),
    )
    db.add(store)
    pending.status = "claimed"
    db.commit()
    set_company_context(db, company_id)
    db.refresh(store)
    store_id = store.id

    pending.created_store_id = store_id
    db.commit()

    return StorePurchaseStatusOut(
        status="claimed",
        store=StoreCreateOut(id=store_id, name=pending_name, city=pending_city, edge_api_key=plaintext_key),
    )


# --- Aquisição por link de marketing (paga ANTES de existir conta) -------
#
# Diferente de /subscribe (exige login — é pra quem já tem conta VigIA
# ampliando o plano), este é o link que vira material de marketing: quem
# clica ainda não tem cadastro nenhum. Cada clique gera uma sessão de
# Checkout nova no Asaas (evita que o link fique velho/expirado num
# anúncio) e redireciona pra lá; depois de pago, o Asaas manda o cliente
# de volta pro cadastro do VigIA já com o pagamento resolvido.

@router.get("/prepaid-checkout")
@limiter.limit("10/minute")
def create_prepaid_checkout(request: Request, packages: int = 1, db: Session = Depends(get_db)):
    if packages < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escolha ao menos 1 pacote de câmeras")

    monthly_value = packages * PRICE_PER_PACKAGE
    claim_token = secrets.token_urlsafe(32)

    success_url = f"{APP_BASE_URL}/?prepaid_token={claim_token}"
    # Sem página de cancelamento dedicada — volta pra tela inicial do
    # dashboard (login/cadastro normal), sem nenhum estado especial.
    cancel_url = APP_BASE_URL

    # Cobra só a primeira mensalidade agora (avulso/DETACHED) — a
    # assinatura recorrente de verdade nasce no cadastro, quando o
    # prepaid_token é reivindicado (ver claim em routers/auth.py).
    checkout = asaas.create_checkout(
        value=monthly_value,
        name=f"VigIA — {packages} pacote(s)",  # limite de 30 caracteres no Asaas
        description=f"VigIA — {packages} pacote(s) de {CAMERAS_PER_PACKAGE} câmeras ({packages * CAMERAS_PER_PACKAGE} câmeras) — primeira mensalidade",
        success_url=success_url,
        cancel_url=cancel_url,
        external_reference=claim_token,
        minutes_to_expire=PREPAID_CHECKOUT_EXPIRY_MINUTES,
    )

    prepaid = PrepaidCheckout(
        asaas_checkout_id=checkout["id"],
        claim_token=claim_token,
        camera_packages=packages,
        monthly_value=monthly_value,
        status="pending",
    )
    db.add(prepaid)
    db.commit()

    return RedirectResponse(checkout["link"], status_code=status.HTTP_302_FOUND)


# --- Pix inline no próprio cadastro (paga sem sair da tela) --------------
#
# Mesmo princípio do Checkout hospedado acima (paga ANTES de existir
# conta), mas sem redirecionar pra fora do app: o QR Code/copia-e-cola
# aparece na própria tela de cadastro (ver OnboardingScreen no
# dashboard). Diferente do Checkout, aqui SOMOS nós que chamamos
# create_customer — por isso pede nome/email/CPF-CNPJ, que o Checkout
# hospedado deixa o próprio Asaas coletar.

@router.post("/prepaid-pix", response_model=PrepaidPixOut)
@limiter.limit("10/minute")
def create_prepaid_pix(request: Request, payload: PrepaidPixIn, db: Session = Depends(get_db)):
    if payload.camera_packages < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escolha ao menos 1 pacote de câmeras")

    monthly_value = payload.camera_packages * PRICE_PER_PACKAGE
    claim_token = secrets.token_urlsafe(32)

    # external_reference aqui identifica o RESPONSÁVEL que está se
    # cadastrando, não uma empresa (ainda não existe nenhuma) — usamos o
    # próprio claim_token, mesmo valor que vai autenticar o claim depois.
    customer = asaas.create_customer(
        name=payload.owner_name, email=payload.email, cpf_cnpj=payload.cpf_cnpj,
        external_reference=claim_token,
    )
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    payment = asaas.create_payment(
        customer_id=customer["id"],
        value=monthly_value,
        description=f"VigIA — {payload.camera_packages} pacote(s) de {CAMERAS_PER_PACKAGE} câmeras — primeira mensalidade",
        due_date=tomorrow,
    )

    prepaid = PrepaidCheckout(
        asaas_payment_id=payment["id"],
        claim_token=claim_token,
        camera_packages=payload.camera_packages,
        monthly_value=monthly_value,
        status="pending",
        asaas_customer_id=customer["id"],
    )
    db.add(prepaid)
    db.commit()

    qr = _get_pix_qr_code_or_none(payment["id"])
    return PrepaidPixOut(
        claim_token=claim_token,
        monthly_value=monthly_value,
        pix_qr_code_image=qr.get("encodedImage") if qr else None,
        pix_copy_paste=qr.get("payload") if qr else None,
        pix_expiration=qr.get("expirationDate") if qr else None,
    )


@router.get("/prepaid-pix/{claim_token}/status", response_model=PrepaidPixStatusOut)
@limiter.limit("30/minute")
def prepaid_pix_status(request: Request, claim_token: str, db: Session = Depends(get_db)):
    # Posse do token é a credencial — quem chama ainda não tem conta
    # nenhuma pra autenticar contra (mesmo princípio de set_invite_lookup).
    set_prepaid_checkout_token_lookup(db, claim_token)
    prepaid = db.query(PrepaidCheckout).filter(PrepaidCheckout.claim_token == claim_token).first()
    if prepaid is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cobrança não encontrada")
    return PrepaidPixStatusOut(status=prepaid.status)


def _mark_prepaid_paid(prepaid: PrepaidCheckout, db: Session) -> None:
    if prepaid.status != "pending":
        return
    # Origem por Checkout hospedado: só descobrimos o customer_id agora,
    # a partir do pagamento real gerado pelo checkout -- não confiamos em
    # customer_id vindo do próprio payload do webhook (formato não
    # documentado com certeza pelo Asaas).
    if prepaid.asaas_checkout_id and not prepaid.asaas_customer_id:
        payments = asaas.get_payments_for_checkout(prepaid.asaas_checkout_id)
        if payments:
            prepaid.asaas_customer_id = payments[0].get("customer")
    # Origem por Pix inline (create_payment): asaas_customer_id já foi
    # setado na criação, porque fomos nós mesmos que chamamos
    # create_customer — nada a descobrir aqui.
    prepaid.status = "paid"
    prepaid.paid_at = datetime.datetime.utcnow()


def _handle_checkout_webhook(event: str, body: dict, db: Session) -> dict:
    checkout = body.get("checkout") or {}
    checkout_id = checkout.get("id") or body.get("id")
    # externalReference é o claim_token que a gente mesmo gerou em
    # create_prepaid_checkout — é o jeito mais confiável de cruzar o
    # evento com a nossa linha, já que a doc do Asaas não deixa claro o
    # formato exato do payload de CHECKOUT_PAID em todo caso.
    external_reference = checkout.get("externalReference") or body.get("externalReference")

    if not checkout_id and not external_reference:
        return {"received": True}

    if checkout_id:
        set_prepaid_checkout_id_lookup(db, checkout_id)
    if external_reference:
        set_prepaid_checkout_token_lookup(db, external_reference)

    prepaid = None
    if checkout_id:
        prepaid = db.query(PrepaidCheckout).filter(PrepaidCheckout.asaas_checkout_id == checkout_id).first()
    if prepaid is None and external_reference:
        prepaid = db.query(PrepaidCheckout).filter(PrepaidCheckout.claim_token == external_reference).first()

    if prepaid is None:
        return {"received": True}  # checkout de outro ambiente/já reivindicado, ignora

    if event == "CHECKOUT_PAID" and prepaid.status == "pending":
        _mark_prepaid_paid(prepaid, db)
    elif event == "CHECKOUT_CANCELED" and prepaid.status == "pending":
        prepaid.status = "canceled"
    elif event == "CHECKOUT_EXPIRED" and prepaid.status == "pending":
        prepaid.status = "expired"

    db.commit()
    return {"received": True}


@router.post("/webhook")
async def asaas_webhook(
    request: Request,
    asaas_access_token: str = Header(None, alias="asaas-access-token"),
    db: Session = Depends(get_db),
):
    if not ASAAS_WEBHOOK_TOKEN or asaas_access_token != ASAAS_WEBHOOK_TOKEN:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de webhook inválido")

    body = await request.json()
    event = body.get("event")

    # Eventos de CHECKOUT (fluxo de aquisição por link, ver
    # create_prepaid_checkout acima) têm formato diferente dos eventos de
    # PAYMENT/SUBSCRIPTION abaixo — nada de "payment" no corpo, e a
    # empresa nem existe ainda nesse momento. Tratado à parte.
    if isinstance(event, str) and event.startswith("CHECKOUT_"):
        return _handle_checkout_webhook(event, body, db)

    payment = body.get("payment", {})

    # Cobrança recorrente (assinatura) tem "subscription"; cobrança
    # avulsa de upgrade não tem — nesse caso caímos para o customer_id.
    # Os dois casos precisam resolver para a empresa certa.
    subscription_id = payment.get("subscription")
    customer_id = payment.get("customer")
    checkout_session_id = payment.get("checkoutSession")
    payment_id = payment.get("id")

    if not subscription_id and not customer_id and not checkout_session_id:
        return {"received": True}  # evento sem nada pra cruzar com uma empresa, ignora

    # Não existe usuário logado aqui (é o Asaas chamando, autenticado só
    # pelo token do webhook) — libera o RLS pontualmente pra achar a
    # empresa certa, pelos dois caminhos possíveis. Os dois podem estar
    # ativos ao mesmo tempo na mesma transação sem conflito.
    if subscription_id:
        set_billing_lookup(db, subscription_id)
    if customer_id:
        set_customer_lookup(db, customer_id)

    company = None
    if subscription_id:
        company = db.query(Company).filter(Company.asaas_subscription_id == subscription_id).first()
    if company is None and customer_id:
        company = db.query(Company).filter(Company.asaas_customer_id == customer_id).first()

    if company is None:
        # Pagamento avulso do fluxo de aquisição por link (ver
        # create_prepaid_checkout acima) — nesse momento ainda não existe
        # Company nenhuma, só a linha de PrepaidCheckout, então os dois
        # cruzamentos acima (subscription/customer) não acham nada. Na
        # prática, confirmado com um pagamento real em produção, o Asaas
        # manda PAYMENT_CONFIRMED/PAYMENT_RECEIVED pra esse tipo de
        # cobrança (DETACHED) — não CHECKOUT_PAID — por isso tratamos
        # aqui também, cruzando pelo checkoutSession do pagamento.
        if event in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"):
            prepaid = None
            if checkout_session_id:
                set_prepaid_checkout_id_lookup(db, checkout_session_id)
                prepaid = db.query(PrepaidCheckout).filter(
                    PrepaidCheckout.asaas_checkout_id == checkout_session_id
                ).first()
            if prepaid is None and payment_id:
                # Fluxo Pix inline (create_prepaid_pix, sem checkoutSession
                # nenhum) — cruza direto pelo id do pagamento avulso.
                set_prepaid_payment_id_lookup(db, payment_id)
                prepaid = db.query(PrepaidCheckout).filter(
                    PrepaidCheckout.asaas_payment_id == payment_id
                ).first()
            if prepaid is not None:
                _mark_prepaid_paid(prepaid, db)
                db.commit()
        return {"received": True}  # assinatura/cliente de outro ambiente, ignora

    # Loja adicional comprada por uma empresa já existente (ver
    # purchase_store acima) — o pagamento é avulso, vinculado ao mesmo
    # asaas_customer_id da empresa, então `company` já resolveu acima.
    # Precisa ser checado ANTES do bloco de câmera abaixo: é o mesmo tipo
    # de evento (PAYMENT_CONFIRMED/RECEIVED), mas não deve mexer em
    # camera_limit nem subscription_status — só destrava a criação da loja.
    if payment_id and event in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"):
        set_store_purchase_payment_lookup(db, payment_id)
        store_purchase = db.query(PendingStorePurchase).filter(
            PendingStorePurchase.asaas_payment_id == payment_id,
            PendingStorePurchase.company_id == company.id,
        ).first()
        if store_purchase is not None:
            if store_purchase.status == "pending":
                store_purchase.status = "paid"
                store_purchase.paid_at = datetime.datetime.utcnow()
                db.commit()
            return {"received": True}

    # Mapeamento dos eventos de cobrança do Asaas para o status que o
    # VigIA usa internamente. A lista completa de eventos está na
    # documentação do Asaas — adicione outros conforme for precisando.
    if event in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"):
        company.subscription_status = "active"
        # Só na PRIMEIRA confirmação — renovações mensais seguintes não
        # devem reiniciar a fila de onboarding nem mexer na ordenação do
        # painel admin (ver /v1/admin/onboarding).
        if company.payment_confirmed_at is None:
            company.payment_confirmed_at = datetime.datetime.utcnow()
        # só agora, com pagamento confirmado (seja da assinatura nova ou
        # de um upgrade avulso), o limite de câmeras é efetivamente
        # liberado — soma ao limite existente
        if company.pending_camera_packages:
            company.camera_limit = (company.camera_limit or 0) + (
                company.pending_camera_packages * CAMERAS_PER_PACKAGE
            )
            company.pending_camera_packages = None
    elif event == "PAYMENT_OVERDUE":
        company.subscription_status = "overdue"
    elif event in ("PAYMENT_DELETED", "SUBSCRIPTION_DELETED"):
        company.subscription_status = "canceled"

    db.commit()
    return {"received": True}
