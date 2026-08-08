"""add suppressed events

Revision ID: 7f9e3c345c52
Revises: 677ef0e72c07
Create Date: 2026-08-08 14:00:00.000000

Log de auditoria pras supressoes de alerta feitas pelo correlator local
da box (ver correlator.py no modulo de deteccao) -- sem isso, uma
supressao errada (duas pessoas diferentes com roupa parecida tratadas
como continuacao) fica totalmente invisivel pro dono da loja.

RLS segue o padrao de alerts: SELECT por current_company_id (dono logado
no dashboard) OU lookup_store_id (nao usado aqui, so INSERT precisa
disso); INSERT so por lookup_store_id (a BOX, autenticada por API key).
Sem policy de UPDATE/DELETE de proposito -- e um log de auditoria,
nao deveria ser editavel nem apagavel casualmente.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7f9e3c345c52'
down_revision = '677ef0e72c07'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('suppressed_events',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('store_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('camera_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('matched_camera_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('track_id', sa.Integer(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('appearance_distance', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ),
    sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ),
    sa.ForeignKeyConstraint(['matched_camera_id'], ['cameras.id'], ),
    sa.PrimaryKeyConstraint('id'),
    )

    # --- Row Level Security ---------------------------------------------
    op.execute("""
        DO $$
        BEGIN
            IF (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
                RAISE EXCEPTION
                    'Role de conexao "%" e superuser -- RLS seria ignorado silenciosamente. '
                    'Use uma role sem superuser antes de aplicar esta migracao.',
                    current_user;
            END IF;
        END $$;
    """)

    op.execute("ALTER TABLE suppressed_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE suppressed_events FORCE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY suppressed_events_tenant_isolation ON suppressed_events
        FOR SELECT USING (
            store_id IN (
                SELECT id FROM stores
                WHERE company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            )
        )
    """)
    op.execute("""
        CREATE POLICY suppressed_events_insert ON suppressed_events
        FOR INSERT WITH CHECK (
            store_id = NULLIF(current_setting('app.lookup_store_id', true), '')::uuid
        )
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS suppressed_events_insert ON suppressed_events")
    op.execute("DROP POLICY IF EXISTS suppressed_events_tenant_isolation ON suppressed_events")
    op.execute("ALTER TABLE suppressed_events NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE suppressed_events DISABLE ROW LEVEL SECURITY")

    op.drop_table('suppressed_events')
