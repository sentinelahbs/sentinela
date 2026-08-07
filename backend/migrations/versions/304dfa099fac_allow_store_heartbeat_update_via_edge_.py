"""allow store heartbeat update via edge lookup

Revision ID: 304dfa099fac
Revises: 3a1a7d605a48
Create Date: 2026-08-07 12:49:16.125231

A política de UPDATE em stores (stores_tenant_modify, ver 631f598d049a)
só reconhece app.current_company_id (usuário logado) — a box de
detecção nunca seta isso, autentica só por app.lookup_store_id (ver
set_store_lookup em tenant_context.py). Sem essa policy adicional, o
UPDATE de last_seen_at/onboarding_status feito pelo novo endpoint
POST /v1/stores/{id}/heartbeat era silenciosamente bloqueado pelo RLS
(SELECT funcionava, UPDATE não — SQLAlchemy reportava StaleDataError
"0 rows matched").

Postgres combina múltiplas políticas permissivas do mesmo comando com
OR automaticamente — não precisa mexer na policy existente, só somar
esta.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '304dfa099fac'
down_revision = '3a1a7d605a48'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE POLICY stores_edge_heartbeat_update ON stores
        FOR UPDATE USING (id = NULLIF(current_setting('app.lookup_store_id', true), '')::uuid)
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS stores_edge_heartbeat_update ON stores")
