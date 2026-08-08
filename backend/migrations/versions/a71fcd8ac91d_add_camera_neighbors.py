"""add camera neighbors

Revision ID: a71fcd8ac91d
Revises: 1c46bfaacd78
Create Date: 2026-08-07 20:00:00.000000

Correlacao entre cameras da mesma loja (edge) depende de saber quais
cameras sao fisicamente vizinhas -- isso nao existia em lugar nenhum do
cadastro (nem no backend, nem na config do edge). Essa tabela guarda essa
marcacao manual feita pelo dono da loja no dashboard.

Par nao-ordenado: sempre gravado com camera_id_a < camera_id_b (aplicado
no router, reforcado aqui por CHECK) para nunca duplicar (A,B) e (B,A).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a71fcd8ac91d'
down_revision = '1c46bfaacd78'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('camera_neighbors',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('camera_id_a', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('camera_id_b', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint('camera_id_a < camera_id_b', name='camera_neighbors_ordered_pair'),
    sa.ForeignKeyConstraint(['camera_id_a'], ['cameras.id'], ),
    sa.ForeignKeyConstraint(['camera_id_b'], ['cameras.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('camera_id_a', 'camera_id_b', name='camera_neighbors_unique_pair'),
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

    op.execute("ALTER TABLE camera_neighbors ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE camera_neighbors FORCE ROW LEVEL SECURITY")

    # camera_id_a sozinho basta pro SELECT/DELETE: os dois lados de um par
    # sempre pertencem a mesma loja (garantido no INSERT abaixo), entao
    # nunca existe um par com A de uma empresa e B de outra pra escapar
    # dessa checagem.
    op.execute("""
        CREATE POLICY camera_neighbors_tenant_isolation ON camera_neighbors
        FOR SELECT USING (
            camera_id_a IN (
                SELECT c.id FROM cameras c
                JOIN stores s ON s.id = c.store_id
                WHERE s.company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            )
        )
    """)
    op.execute("""
        CREATE POLICY camera_neighbors_tenant_delete ON camera_neighbors
        FOR DELETE USING (
            camera_id_a IN (
                SELECT c.id FROM cameras c
                JOIN stores s ON s.id = c.store_id
                WHERE s.company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            )
        )
    """)
    op.execute("""
        CREATE POLICY camera_neighbors_insert ON camera_neighbors
        FOR INSERT WITH CHECK (
            camera_id_a IN (
                SELECT c.id FROM cameras c
                JOIN stores s ON s.id = c.store_id
                WHERE s.company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            )
            AND camera_id_b IN (
                SELECT c.id FROM cameras c
                JOIN stores s ON s.id = c.store_id
                WHERE s.company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            )
        )
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS camera_neighbors_insert ON camera_neighbors")
    op.execute("DROP POLICY IF EXISTS camera_neighbors_tenant_delete ON camera_neighbors")
    op.execute("DROP POLICY IF EXISTS camera_neighbors_tenant_isolation ON camera_neighbors")
    op.execute("ALTER TABLE camera_neighbors NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE camera_neighbors DISABLE ROW LEVEL SECURITY")

    op.drop_table('camera_neighbors')
