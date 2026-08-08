"""allow camera lookup via edge store_id

Revision ID: d286a1001090
Revises: a71fcd8ac91d
Create Date: 2026-08-07 20:10:00.000000

A policy de SELECT em cameras (631f598d049a) so cobre app.current_company_id
(usuario logado) -- nunca cobriu app.lookup_store_id (a BOX de deteccao,
autenticada so por X-API-Key da loja, ver get_store_from_edge_key). Sem
isso, receive_alert (alerts.py) nao consegue validar que o camera_id
enviado pela box pertence de fato aquela loja -- a query sempre voltaria
0 linhas, silenciosamente, o mesmo tipo de bug ja visto em
304dfa099fac/7c15c0125e5d.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd286a1001090'
down_revision = 'a71fcd8ac91d'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE POLICY cameras_edge_lookup ON cameras
        FOR SELECT USING (store_id = NULLIF(current_setting('app.lookup_store_id', true), '')::uuid)
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS cameras_edge_lookup ON cameras")
