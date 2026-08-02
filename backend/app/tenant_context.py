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


def set_invite_lookup(db: Session, token: str) -> None:
    """Usado nos endpoints públicos de convite (/v1/invites/{token}), onde
    quem chama ainda não tem conta nem token JWT — a posse do token de
    convite (32 bytes aleatórios) é a própria credencial de acesso a essa
    linha."""
    db.execute(text("SET LOCAL app.lookup_invite_token = :token"), {"token": token})


def set_auth_bootstrap(db: Session) -> None:
    """Usado só nos dois pontos de login/cadastro que precisam localizar
    um User por email SEM ainda saber a empresa (é justamente isso que
    login resolve, e signup precisa checar duplicidade de email entre
    TODAS as empresas). Fora desses dois pontos, nenhuma outra rota deve
    chamar isso — o resto do app já sabe o company_id do usuário logado."""
    db.execute(text("SET LOCAL app.auth_bootstrap = 'true'"))
