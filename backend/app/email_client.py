"""
Envio de email transacional.

Usa SMTP genérico — funciona com qualquer provedor que ofereça um
relay SMTP (Amazon SES, SendGrid, Postmark, Mailgun, até um Gmail
Workspace para testes). Só troca as variáveis de ambiente, sem
mudar código.

Se preferir um provedor via API HTTP em vez de SMTP (ex: Resend,
Postmark API), troca só o método `send` — o resto do app chama só
`EmailClient.send_invite_email(...)`, então a troca fica isolada aqui.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.sendgrid.net")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "naoresponda@suaempresa.com.br")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Sentinela")

# URL do dashboard web — usada para montar o link do convite.
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5173")


class EmailClient:
    def send(self, to_email: str, subject: str, html_body: str, text_body: str):
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
        msg["To"] = to_email
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(EMAIL_FROM, [to_email], msg.as_string())

    def send_invite_email(self, to_email: str, invited_name: str, company_name: str, token: str):
        link = f"{APP_BASE_URL}/aceitar-convite?token={token}"

        subject = f"Você foi convidado(a) para a {company_name} no Sentinela"

        html_body = f"""
        <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
          <p>Olá, {invited_name},</p>
          <p>Você foi convidado(a) para acessar o painel de monitoramento da
          <strong>{company_name}</strong> no Sentinela.</p>
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
            f"Você foi convidado(a) para acessar o painel de monitoramento da {company_name} no Sentinela.\n"
            f"Acesse o link abaixo para criar sua senha:\n{link}\n\n"
            f"Este link expira em 7 dias."
        )

        self.send(to_email, subject, html_body, text_body)
