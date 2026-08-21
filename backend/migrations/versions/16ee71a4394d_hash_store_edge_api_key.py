"""hash store edge api key

Revision ID: 16ee71a4394d
Revises: 80a5ac4f0991
Create Date: 2026-08-20 17:00:00.000000

edge_api_key era guardado em texto puro e comparado com "!=" (nem hash,
nem constant-time) -- um vazamento do banco (backup, dump, role
comprometida) expõe a credencial de toda box de detecção instalada,
sem expiração, pra sempre. Diferente de senha de usuário, não faz
sentido usar bcrypt aqui: a chave já nasce com 256 bits de entropia
aleatória (secrets.token_urlsafe(32)), então não precisa de custo
computacional pra resistir a força bruta -- e as duas rotas que
autenticam a box (get_store_from_edge_key, GET /v1/edge/whoami)
precisam achar a loja por igualdade direta no banco, o que um hash
salgado (bcrypt) não permite sem varrer a tabela inteira linha a linha.
SHA-256 (determinístico) resolve os dois: barato de calcular, e ainda
assim inviável de reverter uma entrada de 256 bits por força bruta.

O backfill roda em Python (não via pgcrypto/digest() do Postgres) de
propósito -- a role de conexão do backend não é superuser (ver guard em
631f598d049a), e CREATE EXTENSION normalmente exige privilégio que essa
role não tem. Volume de lojas é pequeno o bastante pra isso não pesar.
"""
import hashlib

from alembic import op
import sqlalchemy as sa


revision = '16ee71a4394d'
down_revision = '80a5ac4f0991'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # stores tem FORCE ROW LEVEL SECURITY (ver 631f598d049a) -- até a role
    # DONA da tabela fica sujeita às políticas em DML normal, então sem
    # isso o SELECT/UPDATE do backfill abaixo enxergaria 0 linhas (mesmo
    # com linhas reais existindo), passando batido sem erro nenhum. O
    # ALTER COLUMN SET NOT NULL mais abaixo, por ser DDL, ignora RLS e vê
    # a tabela de verdade -- por isso falhava com NotNullViolation mesmo
    # a SELECT do backfill "não achando" nenhuma linha pra preencher.
    # Mesmo bypass que o painel admin usa (stores_admin_bypass/_update).
    conn.execute(sa.text("SET LOCAL app.platform_admin = 'true'"))

    # Trava a tabela pelo resto desta transação: sem isso, um signup ou
    # "adicionar loja" acontecendo bem no meio da migração cria uma linha
    # nova depois do backfill mas antes do ALTER COLUMN ... SET NOT NULL,
    # e a migração inteira falha com NotNullViolation. ACCESS EXCLUSIVE só
    # bloqueia escritas concorrentes por essa janela curta -- elas esperam
    # e completam normalmente assim que esta transação termina, não falham.
    conn.execute(sa.text("LOCK TABLE stores IN ACCESS EXCLUSIVE MODE"))

    op.add_column('stores', sa.Column('edge_api_key_hash', sa.String(), nullable=True))

    # SQL parametrizado cru, não o proxy table()/column() do SQLAlchemy
    # Core: declarar a coluna "id" (uuid no Postgres) como String nesse
    # proxy faz o WHERE do UPDATE não casar nenhuma linha silenciosamente
    # (sem erro nenhum) -- foi exatamente o que causou duas tentativas
    # anteriores falharem aqui com NotNullViolation, mesmo com a tabela
    # travada. Texto puro deixa o driver/Postgres inferir os tipos certos.
    rows = conn.execute(sa.text("SELECT id, edge_api_key FROM stores")).fetchall()
    for row_id, plaintext in rows:
        digest = hashlib.sha256(plaintext.encode()).hexdigest()
        conn.execute(
            sa.text("UPDATE stores SET edge_api_key_hash = :hash WHERE id = :id"),
            {"hash": digest, "id": row_id},
        )

    op.alter_column('stores', 'edge_api_key_hash', nullable=False)
    op.create_unique_constraint('uq_stores_edge_api_key_hash', 'stores', ['edge_api_key_hash'])

    # A policy antiga comparava a coluna em texto puro contra o valor cru
    # que set_edge_api_key_lookup gravava na sessão -- agora o app passa o
    # hash já calculado pra lá (ver tenant_context.py), então a policy só
    # precisa trocar qual coluna compara, não a lógica em si.
    op.execute("DROP POLICY IF EXISTS stores_edge_api_key_lookup ON stores")
    op.execute("""
        CREATE POLICY stores_edge_api_key_lookup ON stores
        FOR SELECT USING (
            edge_api_key_hash = NULLIF(current_setting('app.lookup_edge_api_key', true), '')
        )
    """)

    op.drop_column('stores', 'edge_api_key')


def downgrade():
    # Downgrade é destrutivo por natureza aqui: o hash SHA-256 não é
    # reversível, então não tem como reconstituir o edge_api_key original
    # das boxes já configuradas. Isso invalidaria toda box em campo --
    # documentado, não escondido atrás de um downgrade "silencioso".
    raise NotImplementedError(
        "Downgrade não suportado: SHA-256 não é reversível, não há como "
        "recuperar o edge_api_key em texto puro original. Reverter esta "
        "migração exigiria gerar uma chave NOVA pra cada loja e "
        "reconfigurar toda box em campo manualmente."
    )
