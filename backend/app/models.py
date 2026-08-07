"""
Modelo de dados multi-tenant.

Hierarquia: Empresa (cliente que paga o SaaS) -> Lojas -> Câmeras -> Alertas.
Usuários pertencem a uma Empresa e têm um papel (owner/gestor) que limita
quais lojas eles enxergam — é isso que separa os dados de um cliente do
outro dentro do mesmo banco.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Enum, Float, Text, Boolean, Integer
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


def gen_uuid():
    return str(uuid.uuid4())


# Considerado offline depois de 3 heartbeats perdidos seguidos (heartbeat
# a cada ~60s no lado da box — ver heartbeat_sender do módulo de detecção)
# em vez de 1, pra não marcar como offline por causa de um blink de rede.
ONLINE_THRESHOLD_SECONDS = 180


class AlertStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class UserRole(str, enum.Enum):
    OWNER = "owner"          # dono da conta, vê todas as lojas da empresa
    STORE_MANAGER = "store_manager"  # vê só as lojas atribuídas a ele


class Company(Base):
    """Um cliente pagante do SaaS (uma rede de lojas, por exemplo)."""
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Cobrança via Asaas — preenchidos quando a empresa assina o plano.
    asaas_customer_id = Column(String, nullable=True)
    asaas_subscription_id = Column(String, nullable=True)
    # nullable=False bate com o NOT NULL + server_default aplicados na
    # migração 073ce17c17dc — sem declarar aqui, o autogenerate do
    # Alembic tentava reverter essa constraint na próxima migração.
    subscription_status = Column(String, nullable=False, default="none")  # none | pending | active | overdue | canceled

    # Quantas câmeras a empresa contratou, no total (soma de todos os
    # pacotes de 5). Isso é o que limita quantas câmeras podem ser
    # cadastradas em qualquer loja da empresa, somadas. NOT NULL: o
    # cameras.py compara `current_count >= company.camera_limit`, e isso
    # quebraria com None numa empresa sem nenhuma assinatura ainda.
    camera_limit = Column(Integer, nullable=False, default=0)
    # Guardado no momento do /subscribe, antes da confirmação do
    # pagamento — o camera_limit só é efetivamente aumentado quando o
    # webhook confirma o pagamento (ver routers/billing.py), para não
    # liberar câmeras sem cobrança confirmada.
    pending_camera_packages = Column(Integer, nullable=True)
    # Setado pelo webhook só na PRIMEIRA confirmação de pagamento (não
    # em renovações mensais seguintes) — é o gatilho e a referência de
    # ordenação da fila de onboarding no painel admin (ver routers/admin.py).
    payment_confirmed_at = Column(DateTime, nullable=True)

    stores = relationship("Store", back_populates="company")
    users = relationship("User", back_populates="company")


class Store(Base):
    __tablename__ = "stores"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id"), nullable=False)
    name = Column(String, nullable=False)
    city = Column(String, nullable=True)

    # Chave usada pela BOX de detecção instalada na loja para autenticar
    # ao enviar alertas — diferente do login do gestor no dashboard.
    edge_api_key = Column(String, nullable=False, unique=True)

    # Texto do aviso de monitoramento exibido/afixado na loja — exigido
    # pela LGPD/CLT para transparência com funcionários e clientes.
    monitoring_notice = Column(Text, default=(
        "Ambiente monitorado por câmeras com apoio de inteligência artificial "
        "para fins de segurança patrimonial, conforme LGPD."
    ))
    clip_retention_days = Column(String, default="30")

    # Onboarding pós-pagamento — string livre (não Enum do Postgres) pelo
    # mesmo motivo de Company.subscription_status: evita migração pra
    # adicionar um valor novo no futuro. Valores usados hoje: "pending"
    # (aguardando conexão das câmeras), "in_progress" (pelo menos um
    # heartbeat já chegou), "completed" (validado manualmente pelo admin
    # — nunca automático, câmera online não garante setup correto).
    onboarding_status = Column(String, nullable=False, default="pending")
    # Atualizado a cada heartbeat da box (ver POST /v1/stores/{id}/heartbeat).
    # "Online" é derivado na hora da leitura (last_seen_at recente), não
    # guardado como booleano — evita um job de fundo só pra manter isso
    # atualizado.
    last_seen_at = Column(DateTime, nullable=True)

    @property
    def online(self) -> bool:
        if self.last_seen_at is None:
            return False
        return (datetime.utcnow() - self.last_seen_at).total_seconds() < ONLINE_THRESHOLD_SECONDS

    company = relationship("Company", back_populates="stores")
    cameras = relationship("Camera", back_populates="store")
    alerts = relationship("Alert", back_populates="store")


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    store_id = Column(UUID(as_uuid=False), ForeignKey("stores.id"), nullable=False)
    label = Column(String, nullable=False)   # ex: "Câmera 03 — Corredor 2"
    active = Column(Boolean, default=True)

    store = relationship("Store", back_populates="cameras")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id"), nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.STORE_MANAGER)
    # Se STORE_MANAGER: lista de store_ids que ele pode ver.
    # (Em produção isso vira uma tabela associativa; simplificado aqui.)
    assigned_store_ids = Column(Text, default="")

    # Acesso ao painel administrativo interno do VigIA (não confundir com
    # UserRole.OWNER, que é "dono da conta de uma empresa cliente" — isso
    # aqui é "funcionário seu, da equipe do VigIA").
    is_platform_admin = Column(Boolean, nullable=False, default=False)

    company = relationship("Company", back_populates="users")


class TeamInvite(Base):
    """Convite pendente. Não cria o usuário ainda — só quando a pessoa
    convidada clica no link do email e define a própria senha
    (fluxo mais seguro que gerar senha temporária e mostrar na tela)."""
    __tablename__ = "team_invites"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id"), nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    store_ids = Column(Text, default="")  # comma-separated
    token = Column(String, nullable=False, unique=True)
    invited_by_user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PasswordResetToken(Base):
    """Token de recuperação de senha. Mesmo princípio do TeamInvite: a
    posse do token (32 bytes aleatórios) é a credencial — sem ela, quem
    pede a redefinição ainda não conseguiu entrar na própria conta."""
    __tablename__ = "password_reset_tokens"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id"), nullable=False)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    token = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    store_id = Column(UUID(as_uuid=False), ForeignKey("stores.id"), nullable=False)
    camera_id = Column(UUID(as_uuid=False), ForeignKey("cameras.id"), nullable=True)
    camera_label = Column(String, nullable=False)

    confidence = Column(Float, nullable=False)
    reason = Column(String, nullable=False)   # explicação da regra que disparou

    clip_url = Column(String, nullable=False)       # onde o clipe está armazenado
    thumbnail_url = Column(String, nullable=True)

    status = Column(Enum(AlertStatus), default=AlertStatus.PENDING)
    reviewed_by_user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    store = relationship("Store", back_populates="alerts")
