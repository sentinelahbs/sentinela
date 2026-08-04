"""
Cliente da API do Asaas — usado para cobrar a assinatura mensal dos
clientes do VigIA via Pix.

Documentação oficial: https://docs.asaas.com. Como toda API de terceiros,
os detalhes podem mudar — confira a documentação atual antes de ir para
produção, especialmente os endpoints de assinatura e webhook.

Fluxo implementado aqui:
  1. Criar o cliente no Asaas (empresa que vai pagar)
  2. Criar a assinatura (recorrência mensal, cobrança via Pix)
  3. Buscar o QR Code Pix da primeira cobrança gerada pela assinatura
  4. Receber webhooks do Asaas confirmando pagamento, para liberar/suspender
     o acesso da empresa no VigIA (isso fica em routers/billing.py)
"""

import os
import requests

ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY", "")
# Sandbox por padrão — troque para a URL de produção só quando for cobrar de verdade.
ASAAS_BASE_URL = os.environ.get("ASAAS_BASE_URL", "https://sandbox.asaas.com/api/v3")


class AsaasClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "access_token": ASAAS_API_KEY,
            "Content-Type": "application/json",
        })

    def create_customer(self, name: str, email: str, cpf_cnpj: str, external_reference: str):
        """external_reference = o company_id do VigIA, para conseguirmos
        cruzar o cliente do Asaas com a empresa aqui no nosso banco."""
        resp = self.session.post(f"{ASAAS_BASE_URL}/customers", json={
            "name": name,
            "email": email,
            "cpfCnpj": cpf_cnpj,
            "externalReference": external_reference,
        })
        resp.raise_for_status()
        return resp.json()  # inclui "id" (ex: "cus_xxx")

    def create_subscription(self, customer_id: str, value: float, description: str, next_due_date: str):
        """next_due_date no formato 'YYYY-MM-DD'. Cobrança recorrente
        mensal, via Pix."""
        resp = self.session.post(f"{ASAAS_BASE_URL}/subscriptions", json={
            "customer": customer_id,
            "billingType": "PIX",
            "cycle": "MONTHLY",
            "value": value,
            "nextDueDate": next_due_date,
            "description": description,
        })
        resp.raise_for_status()
        return resp.json()  # inclui "id" (ex: "sub_xxx")

    def update_subscription(self, subscription_id: str, value: float, description: str):
        """Atualiza o VALOR da recorrência a partir do próximo ciclo —
        usado quando a empresa compra mais pacotes de câmera e já tem
        assinatura ativa, em vez de criar uma segunda assinatura solta."""
        resp = self.session.put(f"{ASAAS_BASE_URL}/subscriptions/{subscription_id}", json={
            "value": value,
            "description": description,
        })
        resp.raise_for_status()
        return resp.json()

    def create_payment(self, customer_id: str, value: float, description: str, due_date: str):
        """Cobrança avulsa (não recorrente) — usada para cobrar AGORA a
        diferença de um upgrade de pacotes no meio do ciclo, enquanto a
        assinatura recorrente já foi ajustada para refletir o novo total
        a partir do próximo mês."""
        resp = self.session.post(f"{ASAAS_BASE_URL}/payments", json={
            "customer": customer_id,
            "billingType": "PIX",
            "value": value,
            "dueDate": due_date,
            "description": description,
        })
        resp.raise_for_status()
        return resp.json()  # inclui "id" (ex: "pay_xxx")

    def get_payments_for_subscription(self, subscription_id: str):
        """A assinatura em si não tem QR Code — quem tem é a cobrança
        (payment) gerada por ela. A primeira cobrança nasce junto com a
        assinatura."""
        resp = self.session.get(
            f"{ASAAS_BASE_URL}/payments", params={"subscription": subscription_id}
        )
        resp.raise_for_status()
        return resp.json().get("data", [])

    def get_pix_qr_code(self, payment_id: str):
        resp = self.session.get(f"{ASAAS_BASE_URL}/payments/{payment_id}/pixQrCode")
        resp.raise_for_status()
        return resp.json()  # inclui "encodedImage" (base64), "payload" (copia-e-cola), "expirationDate"
