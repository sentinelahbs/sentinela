"""allow store lookup via edge api key

Revision ID: 80a5ac4f0991
Revises: dc01c1d1b8a9
Create Date: 2026-08-08 10:00:00.000000

O assistente de configuracao da box (rodando no PC do cliente) so tem a
chave da loja (edge_api_key, mostrada uma vez no dashboard ao criar a
loja) -- ainda nao sabe o store_id, que e exigido em todas as rotas de
box hoje (get_store_from_edge_key). Sem isso, o assistente exigiria que
o dono digitasse os DOIS valores, e o dashboard nunca expos store_id
como algo copiavel (so a chave). Policy nova de SELECT em stores,
escopada por posse da propria chave (mesmo principio de
password_reset_tokens/team_invites) -- usada so por GET /v1/edge/whoami.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '80a5ac4f0991'
down_revision = 'dc01c1d1b8a9'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE POLICY stores_edge_api_key_lookup ON stores
        FOR SELECT USING (
            edge_api_key = NULLIF(current_setting('app.lookup_edge_api_key', true), '')
        )
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS stores_edge_api_key_lookup ON stores")
