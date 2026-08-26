"""add billing_type_switched_at to companies

Revision ID: d7f3b1a924e6
Revises: c4a9d5e17f02
Create Date: 2026-08-26 18:10:00.000000

Troca automatica de Pix pra boleto (DDA) depois da primeira cobranca
confirmada de uma assinatura (ver webhook asaas_webhook em
routers/billing.py). Precisa de um campo dedicado, nao da pra
reaproveitar Company.payment_confirmed_at -- esse nunca e resetado, entao
uma empresa que cancelou e assinou de novo já apareceria com
payment_confirmed_at preenchido mesmo sendo a primeira cobranca da
assinatura NOVA, o que faria a troca nunca acontecer pra quem reassina.

billing_type_switched_at e resetado pra NULL toda vez que uma assinatura
nova nasce (ver "PRIMEIRA ASSINATURA" em subscribe(), routers/billing.py)
-- e' isso que faz o controle ser por assinatura, nao por empresa pra
sempre.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7f3b1a924e6'
down_revision = 'c4a9d5e17f02'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('companies', sa.Column('billing_type_switched_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('companies', 'billing_type_switched_at')
