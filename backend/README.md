# Backend — API central

Esta é a peça que fica no meio de tudo: recebe os alertas gerados pela
**box de detecção** de cada loja, guarda no banco, e alimenta o
**dashboard web/mobile** que o gestor usa pra revisar.

## Estrutura

```
app/
  main.py           → entrypoint FastAPI, junta as rotas
  models.py         → schema multi-tenant (Company -> Store -> Camera -> Alert)
  schemas.py         → validação de entrada/saída (Pydantic)
  database.py         → conexão com Postgres
  auth.py             → dois tipos de autenticação (JWT p/ pessoas, API key p/ boxes)
  storage.py           → upload dos clipes (S3-compatível)
  routers/
    alerts.py           → recebe alertas da box + lista/revisa no dashboard
    auth.py              → login do gestor
    stores.py            → lista de lojas (alimenta o seletor no dashboard)
```

## Por que dois tipos de autenticação

- **API key por loja** (header `X-API-Key`): usada pela box de detecção
  quando ela envia um alerta (`POST /v1/stores/{id}/alerts`). É uma
  credencial de dispositivo, não de pessoa — não faz sentido pedir login
  humano de um processo automatizado.
- **JWT (login com email/senha)**: usado pelo dashboard, quando um gestor
  faz login para revisar alertas. Todo endpoint consumido pelo
  dashboard checa `company_id` do usuário contra a empresa dona da loja —
  é isso que garante que o cliente A nunca veja dados do cliente B
  (isolamento multi-tenant).

## Rodando localmente

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # depois edite com suas credenciais reais
uvicorn app.main:app --reload
```

A API sobe em `http://localhost:8000`. Documentação interativa automática
em `http://localhost:8000/docs`.

Precisa de um Postgres rodando localmente (ou ajuste `DATABASE_URL` no
`.env` para outro banco). Se quiser algo rápido pra testar sem instalar
Postgres à mão:

```bash
docker run --name lp-postgres -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=lossprevention -p 5432:5432 -d postgres:16
```

## Conectando com as outras partes já construídas

- O **dashboard web** (artifact React já criado) chamaria
  `GET /v1/stores` para popular a sidebar, e `GET /v1/stores/{id}/alerts` +
  `PATCH /v1/alerts/{id}` para o feed e os botões de revisão.
- O **módulo de detecção** (`edge-detection/alert_client.py`, já criado)
  chama `POST /v1/stores/{id}/alerts` com o clipe e os metadados do evento.

## Convite de equipe por email

`POST /v1/team/invite` (dono da conta) não cria a conta na hora — cria um
convite pendente com um token e dispara um email real (via SMTP, ver
`email_client.py`) com um link tipo `{APP_BASE_URL}/aceitar-convite?token=...`.
A pessoa convidada abre o link, o front chama `GET /v1/invites/{token}`
para mostrar os detalhes, e `POST /v1/invites/{token}/accept` para criar
a própria senha — só nesse momento a conta é criada. O convite expira em
7 dias.

Configure as variáveis `SMTP_*` e `EMAIL_FROM*` no `.env` com as
credenciais do seu provedor (SendGrid, SES, Postmark etc. — qualquer um
que ofereça relay SMTP funciona sem mudar código).

## Já em produção

- Migrações reais via Alembic (`alembic upgrade head`), `AUTO_CREATE_TABLES=false`
- `ALLOWED_ORIGINS` restrito ao domínio real do dashboard (CORS)
- Rate limiting por IP em login e cadastro (`rate_limit.py`)
- Cloudflare Turnstile (CAPTCHA) no login e cadastro

## O que falta para produção

- Tabela associativa real para `assigned_store_ids` (hoje simplificada,
  campo de texto)
- Rate limiting no endpoint de recebimento de alertas (`POST
  /v1/stores/{id}/alerts`) — hoje só login/cadastro são limitados; uma
  box com bug em loop ainda pode saturar o backend
- Job assíncrono aplicando a política de retenção (`clip_retention_days`)
  de cada loja — apagar clipes automaticamente após o prazo. Hoje isso só
  é coberto se o bucket S3 tiver uma regra de expiração configurada
  manualmente (ver `DEPLOY.md`), não pelo backend
- Testes automatizados dos endpoints
