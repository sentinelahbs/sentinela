"""
Cobrança da assinatura mensal via Pix (Asaas) — em pacotes de câmeras.

Modelo de preço: cada pacote libera 5 câmeras por R$ 349,00/mês. A
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

import os
import time
import datetime

import requests
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from sqlalchemy.orm import Session

from database import get_db
from models import User, Company, Camera, Store, UserRole
from schemas import SubscribeIn, SubscribeOut, BillingStatusOut
from auth import get_current_user
from asaas_client import AsaasClient
from tenant_context import set_company_context, set_billing_lookup, set_customer_lookup

router = APIRouter(prefix="/v1/billing", tags=["billing"])
asaas = AsaasClient()

# Preço por pacote de câmeras — mude aqui se o valor ou o tamanho do
# pacote mudar; é a única fonte de verdade usada tanto na cobrança
# quanto na exibição no dashboard/admin.
CAMERAS_PER_PACKAGE = 5
PRICE_PER_PACKAGE = 349.00

# Token que você define no painel do Asaas (Configurações -> Webhooks)
# e o Asaas envia de volta em todo webhook, para provarmos que a
# requisição realmente veio de lá, não de qualquer um na internet.
ASAAS_WEBHOOK_TOKEN = os.environ.get("ASAAS_WEBHOOK_TOKEN", "")


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
    payment = body.get("payment", {})

    # Cobrança recorrente (assinatura) tem "subscription"; cobrança
    # avulsa de upgrade não tem — nesse caso caímos para o customer_id.
    # Os dois casos precisam resolver para a empresa certa.
    subscription_id = payment.get("subscription")
    customer_id = payment.get("customer")

    if not subscription_id and not customer_id:
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
        return {"received": True}  # assinatura/cliente de outro ambiente, ignora

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
