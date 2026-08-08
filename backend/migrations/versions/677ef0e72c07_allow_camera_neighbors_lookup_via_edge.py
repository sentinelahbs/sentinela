"""allow camera neighbors lookup via edge store_id

Revision ID: 677ef0e72c07
Revises: a5d350d32ad8
Create Date: 2026-08-07 22:00:00.000000

A policy de SELECT em camera_neighbors (a71fcd8ac91d) so cobre
app.current_company_id (usuario logado no dashboard) -- a BOX de
deteccao, autenticada so por X-API-Key da loja (ver
get_store_from_edge_key), nao consegue ler a vizinhanca cadastrada.
Necessario pro correlator local buscar quais cameras sao vizinhas da
sua ao iniciar (ver GET .../cameras/{camera_id}/neighbor-ids).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '677ef0e72c07'
down_revision = 'a5d350d32ad8'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE POLICY camera_neighbors_edge_lookup ON camera_neighbors
        FOR SELECT USING (
            camera_id_a IN (
                SELECT id FROM cameras
                WHERE store_id = NULLIF(current_setting('app.lookup_store_id', true), '')::uuid
            )
        )
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS camera_neighbors_edge_lookup ON camera_neighbors")
