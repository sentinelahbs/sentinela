"""add alerts admin delete policy

Revision ID: a5d350d32ad8
Revises: d286a1001090
Create Date: 2026-08-07 20:30:00.000000

alerts nunca teve nenhuma policy de DELETE (so SELECT/UPDATE/INSERT) --
RLS forcado bloqueia silenciosamente qualquer DELETE ate isso existir.
Necessario pra limpeza administrativa (ex: alertas de teste/smoke test
gravados por engano numa loja real).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a5d350d32ad8'
down_revision = 'd286a1001090'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE POLICY alerts_admin_delete ON alerts
        FOR DELETE USING (current_setting('app.platform_admin', true) = 'true')
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS alerts_admin_delete ON alerts")
