# Imagem de produção do backend. Multi-stage não é necessário aqui porque
# não há passo de build (Python interpretado), mas mantemos a imagem
# enxuta com slim + só as dependências de sistema que o psycopg2 precisa.

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Usuário não-root — evita rodar o processo da API como root no container.
# Criado antes das cópias abaixo pra poder já dar posse dos arquivos a ele
# (alembic precisa escrever novos arquivos de migração em /migrations).
RUN useradd --create-home appuser

COPY --chown=appuser:appuser app/ .

# Migrações do Alembic — copiadas como irmãs de /app (não dentro dela),
# pra bater com o caminho relativo que migrations/env.py espera
# (sys.path aponta pra "../app" a partir de migrations/).
COPY --chown=appuser:appuser alembic.ini /alembic.ini
COPY --chown=appuser:appuser migrations/ /migrations

USER appuser

EXPOSE 8000

# --workers ajustável por CPU disponível no serviço contratado.
# Em produção real, um processo à parte (ex: gunicorn + uvicorn workers)
# tende a ser mais robusto que uvicorn sozinho sob carga.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
