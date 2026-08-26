"""add camera remote calibration

Revision ID: a3f7c9e21b4d
Revises: f784b3aad5c6
Create Date: 2026-08-26 14:00:00.000000

Sincronizacao remota de calibracao (ver calibration_sync.py no modulo de
deteccao): a box passa a buscar periodicamente a zona de interesse e os
thresholds da propria camera no backend, em vez de depender so do que foi
digitado no box_config.json na instalacao.

Todos os 4 campos ficam NULLABLE de proposito -- NULL significa "sem
calibracao remota definida ainda", e nesse caso a box continua usando os
defaults locais que ja existem em config.py (_DEFAULT_ZONE,
_DEFAULT_HAND_STILL_FRAMES, _DEFAULT_MIN_CONFIDENCE). So quando um valor
vem preenchido aqui e que ele passa a sobrescrever o default local --
evita ter que fazer backfill de valor nenhum pras cameras ja cadastradas.

calibration_updated_at e o campo que a box usa pra saber se precisa
reaplicar algo (comparar timestamp e mais barato que comparar payload
inteiro a cada ciclo) -- so avanca quando alguem de fato salva uma
calibracao nova (dashboard do dono ou painel admin durante o piloto).

Politica de UPDATE por admin em cameras nao existia ainda (so SELECT
via cameras_admin_bypass e DELETE via cameras_admin_delete, ver
2c999006f372 e f784b3aad5c6) -- precisa pro painel admin poder editar
calibracao de qualquer loja durante a fase de piloto, sem depender do
dono da loja mexer no dashboard.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = 'a3f7c9e21b4d'
down_revision = 'f784b3aad5c6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('cameras', sa.Column('zone_of_interest', JSONB, nullable=True))
    op.add_column('cameras', sa.Column('hand_still_frames_threshold', sa.Integer(), nullable=True))
    op.add_column('cameras', sa.Column('min_confidence_to_alert', sa.Float(), nullable=True))
    op.add_column('cameras', sa.Column('calibration_updated_at', sa.DateTime(), nullable=True))

    op.execute("""
        CREATE POLICY cameras_admin_update ON cameras
        FOR UPDATE USING (current_setting('app.platform_admin', true) = 'true')
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS cameras_admin_update ON cameras")

    op.drop_column('cameras', 'calibration_updated_at')
    op.drop_column('cameras', 'min_confidence_to_alert')
    op.drop_column('cameras', 'hand_still_frames_threshold')
    op.drop_column('cameras', 'zone_of_interest')
