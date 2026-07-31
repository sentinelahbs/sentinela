import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from database import engine
from models import Base
from rate_limit import limiter
from routers import alerts, auth, stores, team

app = FastAPI(title="Loss Prevention API", version="0.1.0")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ALLOWED_ORIGINS: lista separada por vírgula (ex: o domínio do dashboard
# web publicado). "*" só é aceitável em desenvolvimento local.
allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(stores.router)
app.include_router(alerts.router)
app.include_router(team.router)
app.include_router(team.invite_router)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.on_event("startup")
def on_startup():
    # Em produção, o schema é gerenciado pelo Alembic (ver migrations/ e
    # o passo de deploy que roda `alembic upgrade head`), não por
    # create_all. Deixamos create_all como atalho só para rodar local
    # sem precisar gerar migração na primeira vez — controlado por env var.
    if os.environ.get("AUTO_CREATE_TABLES", "false").lower() == "true":
        Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}
