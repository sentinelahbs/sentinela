"""
Envio de email transacional via API HTTP do SendGrid.

Usava SMTP genérico antes, mas várias hospedagens (Railway incluída)
bloqueiam ou têm instabilidade em conexões de saída na porta de SMTP,
o que travava a requisição inteira sem nunca dar erro nem timeout.
API HTTP por HTTPS (porta 443) não tem esse problema.

Se trocar de provedor de email, troca só o método `send` — o resto do
app chama só `EmailClient.send_invite_email(...)`, a troca fica
isolada aqui.
"""

import os
import requests

# Reaproveita a variável SMTP_PASSWORD como chave de API do SendGrid —
# é o mesmo valor (a API key), só muda como ela é usada por baixo dos panos.
SENDGRID_API_KEY = os.environ.get("SMTP_PASSWORD", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "naoresponda@suaempresa.com.br")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "VigIA")

# URL do dashboard web — usada para montar o link do convite.
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5173")


LOGO_HTML = """
<div style="text-align:center; padding: 20px 0 24px; border-bottom: 1px solid #eee; margin-bottom: 24px;">
  <span style="font-family: sans-serif; font-size: 22px; font-weight: 700; color:#171A21; letter-spacing: -0.01em;">
    🛡️ vig<span style="color:#B9790E;">IA</span>
  </span>
</div>
"""


class EmailClient:
    def send(self, to_email: str, subject: str, html_body: str, text_body: str):
        response = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": EMAIL_FROM, "name": EMAIL_FROM_NAME},
                "subject": subject,
                "content": [
                    {"type": "text/plain", "value": text_body},
                    {"type": "text/html", "value": html_body},
                ],
            },
            # Timeout curto — nunca deixa o pedido do usuário travado
            # esperando o provedor de email responder.
            timeout=10,
        )
        response.raise_for_status()

    def send_welcome_email(self, to_email: str, owner_name: str, company_name: str):
        subject = f"Bem-vindo(a) ao VigIA, {owner_name}"

        html_body = f"""
        <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
          {LOGO_HTML}
          <p>Olá, {owner_name},</p>
          <p>Sua conta e a primeira loja da <strong>{company_name}</strong> já
          estão prontas no VigIA.</p>
          <p style="margin: 24px 0;">
            <a href="{APP_BASE_URL}"
               style="background:#F2A93B;color:#1a1200;padding:10px 18px;
                      border-radius:8px;text-decoration:none;font-weight:600;">
              Acessar o painel
            </a>
          </p>
          <p style="color:#888;font-size:13px;">
            A chave de acesso da loja (usada pra conectar a câmera) fica
            disponível dentro do painel, na tela da própria loja.
          </p>
        </div>
        """

        text_body = (
            f"Olá, {owner_name},\n\n"
            f"Sua conta e a primeira loja da {company_name} já estão prontas no VigIA.\n"
            f"Acesse o painel em: {APP_BASE_URL}\n\n"
            f"A chave de acesso da loja fica disponível dentro do painel, na tela da própria loja."
        )

        self.send(to_email, subject, html_body, text_body)

    def send_invite_email(self, to_email: str, invited_name: str, company_name: str, token: str):
        link = f"{APP_BASE_URL}/aceitar-convite?token={token}"

        subject = f"Você foi convidado(a) para a {company_name} no VigIA"

        html_body = f"""
        <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
          {LOGO_HTML}
          <p>Olá, {invited_name},</p>
          <p>Você foi convidado(a) para acessar o painel de monitoramento da
          <strong>{company_name}</strong> no VigIA.</p>
          <p style="margin: 24px 0;">
            <a href="{link}"
               style="background:#F2A93B;color:#1a1200;padding:10px 18px;
                      border-radius:8px;text-decoration:none;font-weight:600;">
              Aceitar convite e criar senha
            </a>
          </p>
          <p style="color:#888;font-size:13px;">
            Este link expira em 7 dias. Se você não esperava este convite,
            pode ignorar este email.
          </p>
        </div>
        """

        text_body = (
            f"Olá, {invited_name},\n\n"
            f"Você foi convidado(a) para acessar o painel de monitoramento da {company_name} no VigIA.\n"
            f"Acesse o link abaixo para criar sua senha:\n{link}\n\n"
            f"Este link expira em 7 dias."
        )

        self.send(to_email, subject, html_body, text_body)
