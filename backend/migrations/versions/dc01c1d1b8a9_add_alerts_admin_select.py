"""add alerts admin select

Revision ID: dc01c1d1b8a9
Revises: 7f9e3c345c52
Create Date: 2026-08-08 05:00:00.000000

Descoberta testando a limpeza de alertas de teste: pro Postgres, um
DELETE nao usa so a policy de DELETE (alerts_admin_delete, ver
a5d350d32ad8) -- ele TAMBEM exige que a linha seja visivel por alguma
policy de SELECT, combinando os dois com AND (confirmado via EXPLAIN).
alerts_tenant_isolation (SELECT) nunca teve bypass de platform_admin,
entao alerts_admin_delete sozinho nunca funcionava de verdade -- só
funcionava se current_company_id TAMBEM estivesse setado pra empresa
certa. prepaid_checkouts ja tinha esse bypass embutido na propria policy
de SELECT desde o inicio (a71fcd8ac91d) por isso nunca deu esse problema
la. Aqui corrige do mesmo jeito, como uma policy adicional (permissivas
do mesmo comando se combinam com OR, entao isso soma sem alterar
alerts_tenant_isolation existente).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dc01c1d1b8a9'
down_revision = '7f9e3c345c52'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE POLICY alerts_admin_select ON alerts
        FOR SELECT USING (current_setting('app.platform_admin', true) = 'true')
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS alerts_admin_select ON alerts")
