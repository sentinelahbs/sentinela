"""allow admin to update store onboarding status

Revision ID: 7c15c0125e5d
Revises: 304dfa099fac
Create Date: 2026-08-07 12:55:46.555115

A migração 073ce17c17dc deu ao painel admin (app.platform_admin) bypass
de RLS só pra SELECT em companies/stores/users — nenhuma rota de
UPDATE cross-empresa existia até agora. O botão de status na tela de
onboarding (PATCH /v1/admin/stores/{id}/onboarding) é o primeiro
UPDATE do admin numa loja de uma empresa que não é a dele — sem essa
policy, ficava bloqueado do mesmo jeito que o heartbeat da box
(ver 304dfa099fac): SELECT funciona, UPDATE falha silenciosamente
(SQLAlchemy reporta StaleDataError "0 rows matched").
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7c15c0125e5d'
down_revision = '304dfa099fac'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE POLICY stores_admin_update ON stores
        FOR UPDATE USING (current_setting('app.platform_admin', true) = 'true')
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS stores_admin_update ON stores")
