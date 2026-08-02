-- Roda automaticamente na primeira vez que o container do Postgres sobe
-- com um volume vazio (mecanismo padrão da imagem oficial pra scripts em
-- /docker-entrypoint-initdb.d/).
--
-- Cria uma role sem privilégio de superusuário pra API se conectar —
-- isso precisa bater com produção, senão o Row Level Security (RLS) das
-- migrações fica sem efeito nenhum aqui: superuser sempre ignora RLS,
-- mesmo com FORCE ROW LEVEL SECURITY. Ver migrations/versions/
-- 631f598d049a_add_row_level_security.py.
CREATE ROLE vigia_app WITH LOGIN PASSWORD 'vigia_app_local_pw';
GRANT ALL ON SCHEMA public TO vigia_app;
ALTER DATABASE lossprevention OWNER TO vigia_app;
