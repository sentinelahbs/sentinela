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

COPY app/ .

# Usuário não-root — evita rodar o processo da API como root no container
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# --workers ajustável por CPU disponível no serviço contratado.
# Em produção real, um processo à parte (ex: gunicorn + uvicorn workers)
# tende a ser mais robusto que uvicorn sozinho sob carga.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
