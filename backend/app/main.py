import logging
import os
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from database import engine, SessionLocal
from models import Base
from rate_limit import limiter
from routers import alerts, auth, stores, team, billing, admin, cameras, suppressed_events

logger = logging.getLogger("vigia")

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
    # Necessário pro cookie HttpOnly de sessão viajar nas respostas/
    # requisições (fetch com credentials: "include") — sem isso o
    # navegador ignora tanto o Set-Cookie quanto o cookie na volta.
    # Exige que allow_origins seja uma lista explícita (nunca "*"); já é
    # o caso aqui, tanto local quanto em produção.
    allow_credentials=True,
)

app.include_router(auth.router)
app.include_router(stores.router)
app.include_router(alerts.router)
app.include_router(team.router)
app.include_router(team.invite_router)
app.include_router(billing.router)
app.include_router(admin.router)
app.include_router(cameras.router)
app.include_router(suppressed_events.router)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    # ID único por requisição — permite achar nos logs exatamente o que
    # aconteceu num pedido específico, mesmo sem ver o stack trace na hora.
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(f"[{request_id}] Erro não tratado em {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor", "request_id": request_id},
    )


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
    checks = {"database": "ok"}
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception:
        checks["database"] = "erro"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}
