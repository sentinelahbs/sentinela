"""add inline pix prepaid and pending store purchase

Revision ID: c4a9d5e17f02
Revises: b8e14f2a6c93
Create Date: 2026-08-26 17:30:00.000000

Duas coisas novas de cobranca:

1. prepaid_checkouts ganha um segundo jeito de nascer: em vez de sempre
   vir de um Checkout hospedado pelo Asaas (asaas_checkout_id), agora
   tambem pode vir de uma cobranca Pix avulsa criada por nos mesmos,
   inline, sem sair do cadastro (asaas_payment_id) -- ver POST
   /v1/billing/prepaid-pix. asaas_checkout_id vira nullable (so um dos
   dois fica preenchido por linha, nunca os dois nem nenhum). Precisa de
   um lookup novo (app.lookup_prepaid_payment_id) pro webhook achar a
   linha certa quando o evento vem de um payment avulso, nao de um
   checkout.

2. Tabela nova pending_store_purchases: loja adicional comprada por uma
   empresa JA existente (dono logado, "Adicionar loja") passa a ser um
   pagamento avulso de PRICE_PER_PACKAGE antes de a Store nascer de
   verdade -- mesmo principio do prepaid_checkouts, mas dentro de uma
   empresa que ja existe (tem company_id, RLS por tenant normal +
   lookup por payment_id pro webhook, igual os outros pontos de
   cobranca avulsa ja tratados nesse arquivo).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4a9d5e17f02'
down_revision = 'b8e14f2a6c93'
branch_labels = None
depends_on = None


def upgrade():
    # --- prepaid_checkouts: segunda origem possivel (Pix inline) --------
    op.alter_column('prepaid_checkouts', 'asaas_checkout_id', existing_type=sa.String(), nullable=True)
    op.add_column('prepaid_checkouts', sa.Column('asaas_payment_id', sa.String(), nullable=True))
    op.create_unique_constraint('uq_prepaid_checkouts_asaas_payment_id', 'prepaid_checkouts', ['asaas_payment_id'])
    op.create_check_constraint(
        'ck_prepaid_checkouts_exactly_one_origin',
        'prepaid_checkouts',
        '(asaas_checkout_id IS NOT NULL) != (asaas_payment_id IS NOT NULL)',
    )

    op.execute("DROP POLICY IF EXISTS prepaid_checkouts_lookup_select ON prepaid_checkouts")
    op.execute("DROP POLICY IF EXISTS prepaid_checkouts_lookup_update ON prepaid_checkouts")
    op.execute("""
        CREATE POLICY prepaid_checkouts_lookup_select ON prepaid_checkouts
        FOR SELECT USING (
            claim_token = NULLIF(current_setting('app.lookup_prepaid_token', true), '')
            OR asaas_checkout_id = NULLIF(current_setting('app.lookup_prepaid_checkout_id', true), '')
            OR asaas_payment_id = NULLIF(current_setting('app.lookup_prepaid_payment_id', true), '')
            OR current_setting('app.platform_admin', true) = 'true'
        )
    """)
    op.execute("""
        CREATE POLICY prepaid_checkouts_lookup_update ON prepaid_checkouts
        FOR UPDATE USING (
            claim_token = NULLIF(current_setting('app.lookup_prepaid_token', true), '')
            OR asaas_checkout_id = NULLIF(current_setting('app.lookup_prepaid_checkout_id', true), '')
            OR asaas_payment_id = NULLIF(current_setting('app.lookup_prepaid_payment_id', true), '')
        )
    """)

    # --- pending_store_purchases ------------------------------------------
    op.create_table(
        'pending_store_purchases',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('company_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('city', sa.String(), nullable=True),
        sa.Column('asaas_payment_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_store_id', sa.UUID(as_uuid=False), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['created_store_id'], ['stores.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asaas_payment_id'),
    )

    op.execute("ALTER TABLE pending_store_purchases ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE pending_store_purchases FORCE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY pending_store_purchases_tenant_isolation ON pending_store_purchases
        FOR SELECT USING (
            company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            OR asaas_payment_id = NULLIF(current_setting('app.lookup_store_purchase_payment_id', true), '')
            OR current_setting('app.platform_admin', true) = 'true'
        )
    """)
    op.execute("""
        CREATE POLICY pending_store_purchases_tenant_modify ON pending_store_purchases
        FOR UPDATE USING (
            company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            OR asaas_payment_id = NULLIF(current_setting('app.lookup_store_purchase_payment_id', true), '')
        )
    """)
    op.execute("""
        CREATE POLICY pending_store_purchases_insert ON pending_store_purchases
        FOR INSERT WITH CHECK (
            company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
        )
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS pending_store_purchases_insert ON pending_store_purchases")
    op.execute("DROP POLICY IF EXISTS pending_store_purchases_tenant_modify ON pending_store_purchases")
    op.execute("DROP POLICY IF EXISTS pending_store_purchases_tenant_isolation ON pending_store_purchases")
    op.execute("ALTER TABLE pending_store_purchases NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE pending_store_purchases DISABLE ROW LEVEL SECURITY")
    op.drop_table('pending_store_purchases')

    op.execute("DROP POLICY IF EXISTS prepaid_checkouts_lookup_update ON prepaid_checkouts")
    op.execute("DROP POLICY IF EXISTS prepaid_checkouts_lookup_select ON prepaid_checkouts")
    op.execute("""
        CREATE POLICY prepaid_checkouts_lookup_select ON prepaid_checkouts
        FOR SELECT USING (
            claim_token = NULLIF(current_setting('app.lookup_prepaid_token', true), '')
            OR asaas_checkout_id = NULLIF(current_setting('app.lookup_prepaid_checkout_id', true), '')
            OR current_setting('app.platform_admin', true) = 'true'
        )
    """)
    op.execute("""
        CREATE POLICY prepaid_checkouts_lookup_update ON prepaid_checkouts
        FOR UPDATE USING (
            claim_token = NULLIF(current_setting('app.lookup_prepaid_token', true), '')
            OR asaas_checkout_id = NULLIF(current_setting('app.lookup_prepaid_checkout_id', true), '')
        )
    """)
    op.drop_constraint('ck_prepaid_checkouts_exactly_one_origin', 'prepaid_checkouts', type_='check')
    op.drop_constraint('uq_prepaid_checkouts_asaas_payment_id', 'prepaid_checkouts', type_='unique')
    op.drop_column('prepaid_checkouts', 'asaas_payment_id')
    op.alter_column('prepaid_checkouts', 'asaas_checkout_id', existing_type=sa.String(), nullable=False)
