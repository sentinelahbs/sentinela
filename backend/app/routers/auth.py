import datetime
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from limits import parse as parse_rate_limit
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import User, Company, Store, UserRole, PasswordResetToken, PrepaidCheckout
from rate_limit import limiter, get_client_ip
from schemas import (
    LoginIn, SignupIn, SignupOut, MeOut,
    ForgotPasswordIn, ForgotPasswordOut, ResetPasswordIn,
)
from auth import (
    verify_password, hash_password, create_access_token, get_current_user,
    set_auth_cookie, clear_auth_cookie, require_csrf_header, user_to_me_out,
    hash_edge_api_key,
)
from email_client import EmailClient
from turnstile import verify_turnstile
from tenant_context import (
    set_auth_bootstrap, set_company_context, set_password_reset_lookup,
    set_prepaid_checkout_token_lookup,
)
# Preço/pacote e o cliente Asaas já configurado são conceitos de
# billing — reaproveita em vez de duplicar (ver claim do prepaid_token
# abaixo). Sem risco de import circular: billing.py nunca importa nada
# de routers/auth.py.
from routers.billing import CAMERAS_PER_PACKAGE, asaas

router = APIRouter(prefix="/v1/auth", tags=["auth"])
email_client = EmailClient()

RESET_TOKEN_EXPIRY_HOURS = 1

# Limite adicional por email, além do @limiter.limit por IP logo abaixo —
# sem isso, alguém rodando de vários IPs/VPNs conseguiria inundar a caixa
# de entrada de uma única pessoa com emails de redefinição. Chamado direto
# via limiter.limiter (biblioteca `limits`, por baixo do slowapi) porque o
# key_func do decorator @limiter.limit só recebe o Request puro, sem
# acesso ao corpo (email) já parseado pelo FastAPI.
FORGOT_PASSWORD_EMAIL_LIMIT = parse_rate_limit("3/15minutes")


@router.post("/signup", response_model=SignupOut)
@limiter.limit("5/minute")
def signup(request: Request, response: Response, payload: SignupIn, db: Session = Depends(get_db)):
    """Onboarding de um novo cliente do SaaS: cria a empresa, a primeira
    loja (com sua própria API key pra box de detecção) e o usuário owner,
    tudo numa única chamada — é o que alimenta a tela de cadastro."""

    # CSRF primeiro: um token do Turnstile só pode ser verificado uma vez
    # junto ao Cloudflare — se checássemos o Turnstile antes e a requisição
    # fosse barrada aqui embaixo pelo CSRF, o token já teria sido consumido,
    # e uma nova tentativa reusando o mesmo token falharia no Turnstile de
    # forma confusa (widget mostra sucesso, servidor recusa como duplicado).
    require_csrf_header(request)
    if not verify_turnstile(payload.turnstile_token, get_client_ip(request)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Verificação de segurança falhou — tente novamente")

    # Fluxo de aquisição por link (pagou antes de ter conta) — valida o
    # pagamento ANTES de criar qualquer coisa, pra não deixar rastro de
    # empresa/usuário se o token for inválido.
    prepaid = None
    if payload.prepaid_token:
        set_prepaid_checkout_token_lookup(db, payload.prepaid_token)
        prepaid = db.query(PrepaidCheckout).filter(PrepaidCheckout.claim_token == payload.prepaid_token).first()
        if prepaid is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Link de pagamento inválido")
        if prepaid.claimed_at is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este link já foi usado para criar uma conta")
        if prepaid.status != "paid":
            # O Asaas só redireciona pro successUrl depois de pago, mas o
            # nosso webhook (assíncrono) pode não ter processado ainda —
            # front pode reapresentar a mesma tela e tentar de novo.
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Ainda estamos confirmando seu pagamento — aguarde alguns segundos e tente novamente.",
            )

    # Checagem de duplicidade precisa enxergar TODAS as empresas (email é
    # único globalmente) — ainda não existe uma empresa/JWT nesse momento.
    set_auth_bootstrap(db)

    # payload.email já vem normalizado (schemas.py), mas comparar com
    # func.lower() também cobre contas antigas salvas antes dessa correção.
    existing = db.query(User).filter(func.lower(User.email) == payload.email).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma conta com este email")

    if len(payload.password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A senha precisa ter ao menos 8 caracteres")

    if prepaid is not None:
        # O checkout cobrou só a primeira mensalidade avulsa (Pix não
        # suporta RECURRENT no produto de Checkout do Asaas — só cartão,
        # confirmado direto na API). A assinatura recorrente de verdade
        # nasce agora, usando o customer_id resultante daquele pagamento
        # — mesmo create_subscription já usado por quem assina logado
        # em /subscribe. Chamada à API acontece ANTES de criar a empresa
        # de propósito: se falhar, não sobra empresa órfã sem assinatura.
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        subscription = asaas.create_subscription(
            customer_id=prepaid.asaas_customer_id,
            value=prepaid.monthly_value,
            description=(
                f"VigIA — {prepaid.camera_packages} pacote(s) de {CAMERAS_PER_PACKAGE} câmeras "
                f"({prepaid.camera_packages * CAMERAS_PER_PACKAGE} câmeras) — {payload.company_name}"
            ),
            next_due_date=tomorrow,
        )
        prepaid.asaas_subscription_id = subscription["id"]

    company = Company(name=payload.company_name)
    if prepaid is not None:
        # Pagamento já confirmado (checado acima) — a empresa nasce ativa,
        # sem passar pelo /subscribe nem esperar outro webhook.
        company.asaas_customer_id = prepaid.asaas_customer_id
        company.asaas_subscription_id = prepaid.asaas_subscription_id
        company.subscription_status = "active"
        company.payment_confirmed_at = datetime.datetime.utcnow()
        company.camera_limit = prepaid.camera_packages * CAMERAS_PER_PACKAGE
    db.add(company)
    db.flush()  # garante company.id antes de usar como FK
    # Guarda como valor puro: depois do commit() a instância expira, e
    # reler company.id nesse ponto dispararia um SELECT bloqueado pelo
    # RLS (ninguém religou o contexto ainda — é justamente isso que
    # set_company_context faz logo abaixo).
    company_id = company.id

    if prepaid is not None:
        prepaid.claimed_at = datetime.datetime.utcnow()
        prepaid.status = "claimed"
        prepaid.claimed_company_id = company_id

    # Texto puro só existe aqui, local, pra devolver na resposta desta
    # chamada — nunca é persistido (ver Store.edge_api_key_hash).
    store_plaintext_key = secrets.token_urlsafe(32)
    store = Store(
        company_id=company.id,
        name=payload.store_name,
        city=payload.store_city,
        edge_api_key_hash=hash_edge_api_key(store_plaintext_key),
    )
    db.add(store)

    user = User(
        company_id=company.id,
        name=payload.owner_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=UserRole.OWNER,
    )
    db.add(user)

    db.commit()
    # commit() encerra a transação, e junto com ela o SET LOCAL de mais
    # acima — sem isso o RLS não deixaria o refresh() abaixo enxergar as
    # linhas que acabamos de criar (user e store são da mesma company).
    set_company_context(db, company_id)
    db.refresh(user)
    db.refresh(store)

    try:
        email_client.send_welcome_email(
            to_email=user.email,
            owner_name=user.name,
            company_name=payload.company_name,
        )
    except Exception as exc:
        # Não falha o cadastro se o provedor de email tiver soluço — a
        # conta já foi criada. Só loga o erro.
        print(f"[auth] Falha ao enviar email de boas-vindas: {exc}")

    token = create_access_token(user_id=user.id, company_id=company_id)
    set_auth_cookie(response, token)
    return SignupOut(store_id=store.id, store_edge_api_key=store_plaintext_key)


@router.post("/login", response_model=MeOut)
@limiter.limit("10/minute")
def login(request: Request, response: Response, payload: LoginIn, db: Session = Depends(get_db)):
    # CSRF primeiro — ver comentário equivalente em signup() acima: evita
    # queimar o token do Turnstile numa requisição que vai ser recusada
    # de qualquer jeito pelo guard de CSRF.
    require_csrf_header(request)
    if not verify_turnstile(payload.turnstile_token, get_client_ip(request)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Verificação de segurança falhou — tente novamente")

    # Login busca o usuário pelo email antes de saber a empresa dele —
    # é justamente essa consulta que descobre isso.
    set_auth_bootstrap(db)

    user = db.query(User).filter(func.lower(User.email) == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email ou senha inválidos")

    token = create_access_token(user_id=user.id, company_id=user.company_id)
    set_auth_cookie(response, token)
    return user_to_me_out(user)


@router.post("/forgot-password", response_model=ForgotPasswordOut)
@limiter.limit("5/minute")
def forgot_password(request: Request, payload: ForgotPasswordIn, db: Session = Depends(get_db)):
    """Pedido de redefinição de senha. Endpoint público (quem chama ainda
    não conseguiu entrar na própria conta) — por isso a resposta é
    sempre a mesma mensagem genérica, exista ou não conta com esse email:
    sem isso, dava pra descobrir quais emails têm cadastro só testando
    aqui (enumeração de usuários)."""
    if not verify_turnstile(payload.turnstile_token, get_client_ip(request)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Verificação de segurança falhou — tente novamente")

    # Limite por email (ver FORGOT_PASSWORD_EMAIL_LIMIT acima) — aplica
    # mesmo que o email não tenha conta, senão vira um jeito de descobrir
    # que ele não tem limite (o que também vazaria enumeração).
    if not limiter.limiter.hit(FORGOT_PASSWORD_EMAIL_LIMIT, "forgot-password-email", payload.email):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Muitos pedidos de redefinição para este email — aguarde alguns minutos e tente de novo.",
        )

    generic_message = "Se existir uma conta com este email, enviaremos as instruções para redefinir a senha."

    # Busca por email sem ainda saber a empresa — mesmo bootstrap do login.
    set_auth_bootstrap(db)
    user = db.query(User).filter(func.lower(User.email) == payload.email).first()
    if user is None:
        return ForgotPasswordOut(detail=generic_message)

    company_id = user.company_id
    user_id = user.id
    user_name = user.name
    user_email = user.email

    set_company_context(db, company_id)

    # Um pedido novo invalida qualquer token anterior ainda não usado —
    # mesmo padrão do convite de equipe (reenviar substitui o anterior).
    old_tokens = db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user_id,
        PasswordResetToken.used_at.is_(None),
    ).all()
    for old in old_tokens:
        db.delete(old)

    # Valor puro: depois do commit() a instância expira, e reler
    # reset_token.token exigiria um SELECT que o RLS ainda não liberou
    # nesse instante — mais simples guardar o valor antes de inserir.
    token_value = secrets.token_urlsafe(32)
    reset_token = PasswordResetToken(
        company_id=company_id,
        user_id=user_id,
        token=token_value,
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(hours=RESET_TOKEN_EXPIRY_HOURS),
    )
    db.add(reset_token)
    db.commit()

    try:
        email_client.send_password_reset_email(
            to_email=user_email,
            name=user_name,
            token=token_value,
            app=payload.app,
        )
    except Exception as exc:
        # Não falha o pedido se o provedor de email tiver soluço — o
        # token já existe, dá pra pedir de novo. Só loga o erro.
        print(f"[auth] Falha ao enviar email de redefinição de senha: {exc}")

    return ForgotPasswordOut(detail=generic_message)


@router.post("/reset-password", response_model=MeOut)
@limiter.limit("10/minute")
def reset_password(request: Request, response: Response, payload: ResetPasswordIn, db: Session = Depends(get_db)):
    require_csrf_header(request)

    # Quem chama ainda não tem conta acessível — a posse do token é a
    # credencial (igual ao aceite de convite).
    set_password_reset_lookup(db, payload.token)

    reset_token = db.query(PasswordResetToken).filter(PasswordResetToken.token == payload.token).first()
    if reset_token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link de redefinição inválido")
    if reset_token.used_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este link já foi utilizado")
    if reset_token.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este link expirou — peça uma nova redefinição")

    if len(payload.password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A senha precisa ter ao menos 8 caracteres")

    # Valores puros: depois do commit() a instância expira, e reler
    # user_id/company_id exigiria um SELECT que o RLS ainda não liberou
    # nesse instante (o token só prova acesso a essa linha específica).
    user_id = reset_token.user_id
    company_id = reset_token.company_id

    # O token de reset só prova acesso à própria linha em
    # password_reset_tokens — libera o contexto da empresa antes do
    # UPDATE de password_hash no usuário, logo abaixo (mesma transação).
    set_company_context(db, company_id)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado")

    user.password_hash = hash_password(payload.password)
    reset_token.used_at = datetime.datetime.utcnow()
    db.commit()
    # commit() encerra a transação e reseta o SET LOCAL — precisa religar
    # antes do refresh() abaixo (mesmo padrão do signup/aceite de convite),
    # senão o RLS bloqueia o SELECT que o refresh dispara.
    set_company_context(db, company_id)
    db.refresh(user)

    token_value = create_access_token(user_id=user_id, company_id=company_id)
    set_auth_cookie(response, token_value)
    return user_to_me_out(user)


@router.post("/logout")
def logout(request: Request, response: Response):
    require_csrf_header(request)
    clear_auth_cookie(response)
    return {"detail": "Sessão encerrada"}


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    """Usado pelo frontend pra restaurar a sessão ao carregar a página
    (o cookie HttpOnly não pode ser lido por JS, então isso aqui é como
    o front sabe se já está autenticado) e pra saber se essa pessoa tem
    acesso ao painel administrativo interno (is_platform_admin)."""
    return user_to_me_out(user)
