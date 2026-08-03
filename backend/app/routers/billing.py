"""
Cobrança da assinatura mensal via Pix (Asaas).

Dois grupos de endpoint:
  - /v1/billing/subscribe e /v1/billing/status — autenticados, usados
    pelo dashboard (o owner assina o plano, e o sistema consulta o status)
  - /v1/billing/webhook — público, mas protegido por um token compartilhado
    que você configura no painel do Asaas. É o Asaas avisando "esse
    pagamento foi confirmado", não uma pessoa logada chamando.
"""

import os
import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from sqlalchemy.orm import Session

from database import get_db
from models import User, Company, UserRole
from schemas import SubscribeIn, SubscribeOut, BillingStatusOut
from auth import get_current_user
from asaas_client import AsaasClient
from tenant_context import set_company_context, set_billing_lookup

router = APIRouter(prefix="/v1/billing", tags=["billing"])
asaas = AsaasClient()

# Token que você define no painel do Asaas (Configurações -> Webhooks)
# e o Asaas envia de volta em todo webhook, para provarmos que a
# requisição realmente veio de lá, não de qualquer um na internet.
ASAAS_WEBHOOK_TOKEN = os.environ.get("ASAAS_WEBHOOK_TOKEN", "")


@router.post("/subscribe", response_model=SubscribeOut)
def subscribe(
    payload: SubscribeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != UserRole.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas o dono da conta pode assinar o plano")

    company = db.query(Company).filter(Company.id == user.company_id).first()
    # Valores puros: depois de um commit() o SQLAlchemy expira os
    # atributos de todos os objetos da sessão, e reler um atributo do
    # ORM nesse ponto disparava um SELECT que o RLS ainda não liberava
    # (a variável de sessão setada pelo get_current_user só vale até o
    # fim da transação — some no commit). Guardamos aqui pra não
    # depender de reler `company.*` depois de qualquer commit abaixo.
    company_id = company.id
    company_name = company.name
    asaas_customer_id = company.asaas_customer_id

    # cria o cliente no Asaas só na primeira vez — assinaturas seguintes
    # (upgrade de plano, por exemplo) reaproveitam o mesmo customer_id
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

    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    subscription = asaas.create_subscription(
        customer_id=asaas_customer_id,
        value=payload.plan_value,
        description=f"Assinatura VigIA — {company_name}",
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
        return SubscribeOut(subscription_status="pending")

    first_payment_id = payments[0]["id"]
    qr = asaas.get_pix_qr_code(first_payment_id)

    return SubscribeOut(
        subscription_status="pending",
        pix_qr_code_image=qr.get("encodedImage"),
        pix_copy_paste=qr.get("payload"),
        pix_expiration=qr.get("expirationDate"),
    )


@router.get("/status", response_model=BillingStatusOut)
def billing_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == user.company_id).first()
    return BillingStatusOut(subscription_status=company.subscription_status)


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
    subscription_id = payment.get("subscription")

    if not subscription_id:
        return {"received": True}  # evento sem assinatura associada, ignora

    # Não existe usuário logado aqui (é o Asaas chamando, autenticado só
    # pelo token do webhook) — libera o RLS pontualmente pra achar a
    # empresa dona dessa assinatura específica.
    set_billing_lookup(db, subscription_id)
    company = db.query(Company).filter(Company.asaas_subscription_id == subscription_id).first()
    if company is None:
        return {"received": True}  # assinatura de outra integração/ambiente, ignora

    # Mapeamento dos eventos de cobrança do Asaas para o status que o
    # VigIA usa internamente. A lista completa de eventos está na
    # documentação do Asaas — adicione outros conforme for precisando.
    if event in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"):
        company.subscription_status = "active"
    elif event == "PAYMENT_OVERDUE":
        company.subscription_status = "overdue"
    elif event in ("PAYMENT_DELETED", "SUBSCRIPTION_DELETED"):
        company.subscription_status = "canceled"

    db.commit()
    return {"received": True}
