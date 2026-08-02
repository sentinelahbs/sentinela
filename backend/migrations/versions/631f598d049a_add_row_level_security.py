"""add row level security

Revision ID: 631f598d049a
Revises: d192a37a98c9
Create Date: 2026-08-02 01:30:00.000000

Camada extra de isolamento entre empresas, direto no banco — até agora
o isolamento multi-tenant dependia 100% do código da aplicação lembrar
de filtrar por company_id em toda query. Isso continua existindo (não
foi removido), mas agora o Postgres também recusa, por padrão, qualquer
linha fora da empresa da sessão atual — mesmo que uma rota futura
esqueça o filtro.

Como funciona: cada política usa `current_setting('app.*', true)`, uma
variável setada via `SET LOCAL` pelo backend (ver app/tenant_context.py)
assim que a identidade da requisição é conhecida — a partir do JWT pra
gestores logados, ou de forma pontual (lookup por id/token) nos poucos
endpoints que ainda não sabem a empresa nesse momento (login, cadastro,
a BOX de detecção autenticando por API key, aceite de convite). Nenhuma
variável setada = nenhuma linha visível, por padrão.

INSERT foi deixado permissivo (`WITH CHECK (true)`) em todas as tabelas:
quem decide o que é criado e com qual company_id continua sendo o
código da aplicação (que já valida role/dono antes de inserir); o valor
do RLS aqui está em barrar LEITURA e MODIFICAÇÃO de linhas de outras
empresas, que é o cenário de vazamento entre clientes.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '631f598d049a'
down_revision = 'd192a37a98c9'
branch_labels = None
depends_on = None


_TABLES = ["companies", "stores", "users", "team_invites", "alerts", "cameras"]


def upgrade():
    # Guard: se a role atual for superuser, RLS é ignorado pelo Postgres
    # de forma silenciosa e incondicional (regra do próprio banco — não
    # tem como contornar com FORCE ROW LEVEL SECURITY). Abortar aqui é
    # melhor do que aplicar uma proteção que parece existir mas não
    # existe. Se isso disparar em produção, a role de conexão do backend
    # precisa deixar de ser superuser antes de tentar de novo.
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

    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE garante que a política vale mesmo pra role dona da tabela
        # (o backend é dono, pois foi quem criou via migração).
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # --- companies ---------------------------------------------------
    op.execute("""
        CREATE POLICY companies_tenant_isolation ON companies
        FOR SELECT USING (id = NULLIF(current_setting('app.current_company_id', true), '')::uuid)
    """)
    op.execute("""
        CREATE POLICY companies_tenant_modify ON companies
        FOR UPDATE USING (id = NULLIF(current_setting('app.current_company_id', true), '')::uuid)
    """)
    op.execute("""
        CREATE POLICY companies_tenant_delete ON companies
        FOR DELETE USING (id = NULLIF(current_setting('app.current_company_id', true), '')::uuid)
    """)
    op.execute("""
        CREATE POLICY companies_insert ON companies
        FOR INSERT WITH CHECK (true)
    """)

    # --- stores --------------------------------------------------------
    # OR lookup_store_id: usado pela BOX de detecção, que ainda não sabe
    # a company_id da loja no momento de validar a X-API-Key.
    op.execute("""
        CREATE POLICY stores_tenant_isolation ON stores
        FOR SELECT USING (
            company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            OR id = NULLIF(current_setting('app.lookup_store_id', true), '')::uuid
        )
    """)
    op.execute("""
        CREATE POLICY stores_tenant_modify ON stores
        FOR UPDATE USING (company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid)
    """)
    op.execute("""
        CREATE POLICY stores_tenant_delete ON stores
        FOR DELETE USING (company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid)
    """)
    op.execute("""
        CREATE POLICY stores_insert ON stores
        FOR INSERT WITH CHECK (true)
    """)

    # --- users -----------------------------------------------------------
    # OR auth_bootstrap: usado só por login (busca por email) e signup
    # (checagem de email duplicado) — nenhum dos dois sabe a empresa
    # ainda nesse momento.
    op.execute("""
        CREATE POLICY users_tenant_isolation ON users
        FOR SELECT USING (
            company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            OR current_setting('app.auth_bootstrap', true) = 'true'
        )
    """)
    op.execute("""
        CREATE POLICY users_tenant_modify ON users
        FOR UPDATE USING (company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid)
    """)
    op.execute("""
        CREATE POLICY users_tenant_delete ON users
        FOR DELETE USING (company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid)
    """)
    op.execute("""
        CREATE POLICY users_insert ON users
        FOR INSERT WITH CHECK (true)
    """)

    # --- team_invites ----------------------------------------------------
    # OR lookup_invite_token: os endpoints públicos de convite (a pessoa
    # convidada ainda não tem conta) provam acesso pela posse do token.
    op.execute("""
        CREATE POLICY invites_tenant_isolation ON team_invites
        FOR SELECT USING (
            company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            OR token = NULLIF(current_setting('app.lookup_invite_token', true), '')
        )
    """)
    op.execute("""
        CREATE POLICY invites_tenant_modify ON team_invites
        FOR UPDATE USING (
            company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            OR token = NULLIF(current_setting('app.lookup_invite_token', true), '')
        )
    """)
    op.execute("""
        CREATE POLICY invites_tenant_delete ON team_invites
        FOR DELETE USING (company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid)
    """)
    op.execute("""
        CREATE POLICY invites_insert ON team_invites
        FOR INSERT WITH CHECK (true)
    """)

    # --- alerts ------------------------------------------------------
    # Não tem company_id direto — junta com stores. lookup_store_id
    # cobre o POST vindo da BOX de detecção (mesma sessão que validou a
    # X-API-Key logo antes).
    op.execute("""
        CREATE POLICY alerts_tenant_isolation ON alerts
        FOR SELECT USING (
            store_id IN (
                SELECT id FROM stores
                WHERE company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            )
            OR store_id = NULLIF(current_setting('app.lookup_store_id', true), '')::uuid
        )
    """)
    op.execute("""
        CREATE POLICY alerts_tenant_modify ON alerts
        FOR UPDATE USING (
            store_id IN (
                SELECT id FROM stores
                WHERE company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            )
        )
    """)
    op.execute("""
        CREATE POLICY alerts_insert ON alerts
        FOR INSERT WITH CHECK (store_id = NULLIF(current_setting('app.lookup_store_id', true), '')::uuid)
    """)

    # --- cameras ------------------------------------------------------
    # Sem endpoint usando essa tabela ainda hoje — política já pronta
    # pro dia que existir, seguindo o mesmo padrão de alerts.
    op.execute("""
        CREATE POLICY cameras_tenant_isolation ON cameras
        FOR SELECT USING (
            store_id IN (
                SELECT id FROM stores
                WHERE company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            )
        )
    """)
    op.execute("""
        CREATE POLICY cameras_tenant_modify ON cameras
        FOR UPDATE USING (
            store_id IN (
                SELECT id FROM stores
                WHERE company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            )
        )
    """)
    op.execute("""
        CREATE POLICY cameras_tenant_delete ON cameras
        FOR DELETE USING (
            store_id IN (
                SELECT id FROM stores
                WHERE company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            )
        )
    """)
    op.execute("""
        CREATE POLICY cameras_insert ON cameras
        FOR INSERT WITH CHECK (
            store_id IN (
                SELECT id FROM stores
                WHERE company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid
            )
        )
    """)


def downgrade():
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    policies = {
        "companies": ["companies_tenant_isolation", "companies_tenant_modify", "companies_tenant_delete", "companies_insert"],
        "stores": ["stores_tenant_isolation", "stores_tenant_modify", "stores_tenant_delete", "stores_insert"],
        "users": ["users_tenant_isolation", "users_tenant_modify", "users_tenant_delete", "users_insert"],
        "team_invites": ["invites_tenant_isolation", "invites_tenant_modify", "invites_tenant_delete", "invites_insert"],
        "alerts": ["alerts_tenant_isolation", "alerts_tenant_modify", "alerts_insert"],
        "cameras": ["cameras_tenant_isolation", "cameras_tenant_modify", "cameras_tenant_delete", "cameras_insert"],
    }
    for table, names in policies.items():
        for name in names:
            op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
