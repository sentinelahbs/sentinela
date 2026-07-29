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
    Column, String, DateTime, ForeignKey, Enum, Float, Text, Boolean
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


def gen_uuid():
    return str(uuid.uuid4())


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
