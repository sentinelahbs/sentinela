"""add company pause and admin delete rls

Revision ID: f784b3aad5c6
Revises: 16ee71a4394d
Create Date: 2026-08-21 12:20:00.000000

Duas coisas pro painel admin conseguir pausar e excluir empresa de
verdade:

1. Company.access_paused -- suspensao administrativa de ACESSO,
   separada de subscription_status de proposito (esse continua so
   refletindo cobranca, setado pelo webhook do Asaas -- nunca controla
   se o cliente consegue usar o dashboard). Ver get_current_user em
   auth.py.

2. Policies de bypass pro admin (app.platform_admin = 'true') em
   UPDATE/DELETE que faltavam. Descoberto rodando uma checagem real
   contra producao (pg_policies): so alerts tinha DELETE liberado pro
   admin, so stores tinha UPDATE liberado. Sem isso, o DELETE/UPDATE
   do admin roda sem erro nenhum mas afeta 0 linhas -- RLS nega
   silenciosamente, nao levanta excecao. camera_neighbors e
   suppressed_events nem tinham policy de DELETE nenhuma, pra ninguem.
"""
from alembic import op
import sqlalchemy as sa


revision = 'f784b3aad5c6'
down_revision = '16ee71a4394d'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('companies', sa.Column('access_paused', sa.Boolean(), nullable=False, server_default=sa.false()))

    op.execute("""
        CREATE POLICY companies_admin_update ON companies
        FOR UPDATE USING (current_setting('app.platform_admin', true) = 'true')
    """)
    op.execute("""
        CREATE POLICY companies_admin_delete ON companies
        FOR DELETE USING (current_setting('app.platform_admin', true) = 'true')
    """)
    op.execute("""
        CREATE POLICY stores_admin_delete ON stores
        FOR DELETE USING (current_setting('app.platform_admin', true) = 'true')
    """)
    op.execute("""
        CREATE POLICY users_admin_delete ON users
        FOR DELETE USING (current_setting('app.platform_admin', true) = 'true')
    """)
    op.execute("""
        CREATE POLICY cameras_admin_delete ON cameras
        FOR DELETE USING (current_setting('app.platform_admin', true) = 'true')
    """)
    op.execute("""
        CREATE POLICY invites_admin_delete ON team_invites
        FOR DELETE USING (current_setting('app.platform_admin', true) = 'true')
    """)
    op.execute("""
        CREATE POLICY password_reset_tokens_admin_delete ON password_reset_tokens
        FOR DELETE USING (current_setting('app.platform_admin', true) = 'true')
    """)
    op.execute("""
        CREATE POLICY camera_neighbors_admin_delete ON camera_neighbors
        FOR DELETE USING (current_setting('app.platform_admin', true) = 'true')
    """)
    op.execute("""
        CREATE POLICY suppressed_events_admin_delete ON suppressed_events
        FOR DELETE USING (current_setting('app.platform_admin', true) = 'true')
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS suppressed_events_admin_delete ON suppressed_events")
    op.execute("DROP POLICY IF EXISTS camera_neighbors_admin_delete ON camera_neighbors")
    op.execute("DROP POLICY IF EXISTS password_reset_tokens_admin_delete ON password_reset_tokens")
    op.execute("DROP POLICY IF EXISTS invites_admin_delete ON team_invites")
    op.execute("DROP POLICY IF EXISTS cameras_admin_delete ON cameras")
    op.execute("DROP POLICY IF EXISTS users_admin_delete ON users")
    op.execute("DROP POLICY IF EXISTS stores_admin_delete ON stores")
    op.execute("DROP POLICY IF EXISTS companies_admin_delete ON companies")
    op.execute("DROP POLICY IF EXISTS companies_admin_update ON companies")
    op.drop_column('companies', 'access_paused')
