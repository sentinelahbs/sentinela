"""
Pontes entre a autenticação da aplicação e o Row Level Security (RLS) do
Postgres. As políticas de RLS (ver migração add_row_level_security) leem
essas configurações de sessão para decidir quais linhas cada query pode
enxergar — sem chamar uma destas funções antes de consultar o banco, o
RLS nega tudo por padrão.

Todas usam `SET LOCAL`, que vale só até o fim da transação atual e nunca
vaza entre requisições (cada request do FastAPI usa sua própria Session/
transação via `get_db`).
"""

from sqlalchemy import text
from sqlalchemy.orm import Session


def set_company_context(db: Session, company_id: str) -> None:
    """Usado assim que um usuário autentica via JWT — o company_id já vem
    dentro do próprio token (não precisa de query extra pra descobrir),
    então isso roda ANTES da primeira consulta que o RLS precisa filtrar."""
    db.execute(text("SET LOCAL app.current_company_id = :cid"), {"cid": company_id})


def set_store_lookup(db: Session, store_id: str) -> None:
    """Usado pela BOX de detecção (autenticação por API key da loja, não
    por login de pessoa). Nesse momento ainda não sabemos a qual empresa
    a loja pertence — é exatamente isso que a consulta seguinte descobre
    — então liberamos a leitura de uma única linha pelo id que a própria
    requisição informou (não é um vazamento: quem já tem o store_id não
    ganha acesso a outras lojas, só a essa linha específica)."""
    db.execute(text("SET LOCAL app.lookup_store_id = :sid"), {"sid": store_id})


def set_edge_api_key_lookup(db: Session, api_key_hash: str) -> None:
    """Usado só por GET /v1/edge/whoami — o assistente de configuração da
    box tem a chave da loja (mostrada uma vez no dashboard ao criar a
    loja) mas ainda não sabe o store_id, que é o que essa consulta
    resolve. Mesmo princípio de set_invite_lookup: posse da chave é a
    credencial. Diferente de set_store_lookup (que já parte de um
    store_id conhecido), aqui a busca é pelo valor da própria chave.
    Recebe o hash SHA-256 da chave (auth.hash_edge_api_key), não a chave
    em texto puro — a policy de RLS compara contra a coluna
    edge_api_key_hash (ver migração 16ee71a4394d)."""
    db.execute(text("SET LOCAL app.lookup_edge_api_key = :key"), {"key": api_key_hash})


def set_invite_lookup(db: Session, token: str) -> None:
    """Usado nos endpoints públicos de convite (/v1/invites/{token}), onde
    quem chama ainda não tem conta nem token JWT — a posse do token de
    convite (32 bytes aleatórios) é a própria credencial de acesso a essa
    linha."""
    db.execute(text("SET LOCAL app.lookup_invite_token = :token"), {"token": token})


def set_password_reset_lookup(db: Session, token: str) -> None:
    """Usado nos endpoints públicos de recuperação de senha
    (/v1/auth/reset-password), onde quem chama ainda não conseguiu entrar
    na própria conta — igual set_invite_lookup, a posse do token (32
    bytes aleatórios) é a própria credencial de acesso a essa linha."""
    db.execute(text("SET LOCAL app.lookup_reset_token = :token"), {"token": token})


def set_auth_bootstrap(db: Session) -> None:
    """Usado só nos dois pontos de login/cadastro que precisam localizar
    um User por email SEM ainda saber a empresa (é justamente isso que
    login resolve, e signup precisa checar duplicidade de email entre
    TODAS as empresas). Fora desses dois pontos, nenhuma outra rota deve
    chamar isso — o resto do app já sabe o company_id do usuário logado."""
    db.execute(text("SET LOCAL app.auth_bootstrap = 'true'"))


def set_platform_admin_context(db: Session) -> None:
    """Usado só por get_current_admin (auth.py), depois de já confirmar
    is_platform_admin=True — libera visão de TODAS as empresas/lojas/
    usuários, para o painel administrativo interno do VigIA. Nenhuma rota
    de cliente deve chamar isso; é exclusivo do painel admin."""
    db.execute(text("SET LOCAL app.platform_admin = 'true'"))


def set_billing_lookup(db: Session, asaas_subscription_id: str) -> None:
    """Usado só pelo webhook do Asaas (/v1/billing/webhook), que não tem
    usuário logado — é o Asaas avisando sobre um pagamento, autenticado
    pelo token do webhook, não por JWT. Libera a leitura/atualização só
    da empresa dona dessa assinatura específica."""
    db.execute(
        text("SET LOCAL app.lookup_subscription_id = :sid"),
        {"sid": asaas_subscription_id},
    )


def set_customer_lookup(db: Session, asaas_customer_id: str) -> None:
    """Igual set_billing_lookup, mas pelo customer_id — usado quando o
    webhook do Asaas manda uma cobrança AVULSA (upgrade de pacotes), que
    não tem "subscription" associada, só "customer". Os dois lookups do
    webhook podem estar ativos na mesma transação (um cobre cada
    caminho possível de identificar a empresa certa)."""
    db.execute(
        text("SET LOCAL app.lookup_customer_id = :cid"),
        {"cid": asaas_customer_id},
    )


def set_prepaid_checkout_token_lookup(db: Session, token: str) -> None:
    """Usado no cadastro público (/v1/auth/signup?prepaid_token=...) e no
    fallback do webhook de checkout — quem chama ainda não tem conta;
    igual set_invite_lookup, a posse do token é a credencial."""
    db.execute(
        text("SET LOCAL app.lookup_prepaid_token = :token"),
        {"token": token},
    )


def set_prepaid_checkout_id_lookup(db: Session, asaas_checkout_id: str) -> None:
    """Usado pelo webhook do Asaas (evento CHECKOUT_*) — mesmo princípio
    de set_billing_lookup/set_customer_lookup, mas pra achar o registro
    de checkout pré-cadastro, não uma empresa (que ainda não existe
    nesse momento)."""
    db.execute(
        text("SET LOCAL app.lookup_prepaid_checkout_id = :cid"),
        {"cid": asaas_checkout_id},
    )
