"""add prepaid checkouts admin delete policy

Revision ID: 1c46bfaacd78
Revises: 1def4146e621
Create Date: 2026-08-07 19:10:00.000000

prepaid_checkouts nasceu sem nenhuma policy de DELETE (só SELECT/UPDATE/
INSERT) — RLS forçado bloqueia silenciosamente qualquer DELETE até isso
existir. Necessário para limpeza administrativa de checkouts de teste/
abandonados (sessões pending nunca pagas, ex.: cliques duplicados no link
de checkout).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1c46bfaacd78'
down_revision = '1def4146e621'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE POLICY prepaid_checkouts_admin_delete ON prepaid_checkouts
        FOR DELETE USING (current_setting('app.platform_admin', true) = 'true')
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS prepaid_checkouts_admin_delete ON prepaid_checkouts")
