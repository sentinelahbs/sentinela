"""add ai_verdict and ai_justification to alerts

Revision ID: e9a2c7f14b3d
Revises: d7f3b1a924e6
Create Date: 2026-09-02 05:40:00.000000

Segundo parecer de IA sobre alertas ja disparados (ver ai_review.py) --
roda em background depois que o alerta ja foi salvo, preenchendo esses
dois campos quando termina. Ambos ficam NULL ate a analise concluir (ou
pra sempre, se ANTHROPIC_API_KEY nao estiver configurada, ou se a
analise falhar -- e um sinal complementar, nao obrigatorio pro alerta
existir).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e9a2c7f14b3d'
down_revision = 'd7f3b1a924e6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('alerts', sa.Column('ai_verdict', sa.String(), nullable=True))
    op.add_column('alerts', sa.Column('ai_justification', sa.String(), nullable=True))


def downgrade():
    op.drop_column('alerts', 'ai_justification')
    op.drop_column('alerts', 'ai_verdict')
