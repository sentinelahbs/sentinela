"""add camera calibration_updated_by

Revision ID: b8e14f2a6c93
Revises: a3f7c9e21b4d
Create Date: 2026-08-26 16:30:00.000000

Complementa calibration_updated_at (ja existente): agora tambem guarda
QUEM fez a ultima calibracao remota de uma camera. So faz sentido
guardar o admin que mexeu -- calibracao e exclusiva do painel admin
desde a migracao anterior (dono da loja nao tem mais acesso a essa
escrita, ver commit "Restringir calibracao remota de camera ao painel
admin"), entao o unico autor possivel e um User com is_platform_admin.

FK nullable: cameras calibradas antes dessa coluna existir (ou nunca
calibradas) ficam com NULL, sem precisar de backfill.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = 'b8e14f2a6c93'
down_revision = 'a3f7c9e21b4d'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'cameras',
        sa.Column('calibration_updated_by_admin_id', UUID(as_uuid=False), sa.ForeignKey('users.id'), nullable=True),
    )


def downgrade():
    op.drop_column('cameras', 'calibration_updated_by_admin_id')
