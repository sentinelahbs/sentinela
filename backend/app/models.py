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
from sqlalchemy.dialects.postgresql import UUID, JSONB
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

    # Suspensão administrativa do SERVIÇO DE DETECÇÃO, separada de
    # subscription_status de propósito — subscription_status só reflete
    # cobrança (setado pelo webhook do Asaas). access_paused é a ação
    # manual do painel admin ("pausar empresa"): o dashboard continua
    # acessível (precisa mostrar o aviso pro gestor), mas a box para de
    # conseguir registrar alerta novo -- ver receive_alert em
    # routers/alerts.py e MeOut.access_paused (schemas.py).
    access_paused = Column(Boolean, nullable=False, default=False)

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

    # Hash SHA-256 da chave usada pela BOX de detecção instalada na loja
    # para autenticar ao enviar alertas (diferente do login do gestor no
    # dashboard) — o valor em texto puro só existe no momento da criação
    # (mostrado uma vez na resposta da API) e nunca é persistido; ver
    # auth.hash_edge_api_key.
    edge_api_key_hash = Column(String, nullable=False, unique=True)

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

    # Calibração remota (ver calibration_sync.py no módulo de detecção) --
    # NULL = sem calibração remota definida, a box usa os defaults locais
    # de config.py. Formato de zone_of_interest: lista de pares [x,y]
    # normalizados (0-1), mesma convenção do box_config.json.
    zone_of_interest = Column(JSONB, nullable=True)
    hand_still_frames_threshold = Column(Integer, nullable=True)
    min_confidence_to_alert = Column(Float, nullable=True)
    calibration_updated_at = Column(DateTime, nullable=True)
    # Qual admin (equipe VigIA) fez a última calibração -- só existe
    # calibração via painel admin, então o autor é sempre um
    # is_platform_admin (ver update_camera_calibration_admin).
    calibration_updated_by_admin_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    calibrated_by = relationship("User", foreign_keys=[calibration_updated_by_admin_id])

    store = relationship("Store", back_populates="cameras")

    @property
    def calibration_updated_by_name(self):
        # Carrega sob demanda (lazy) só quando o schema pede -- lista de
        # câmeras por loja é pequena, N+1 aqui não é um problema real.
        return self.calibrated_by.name if self.calibrated_by else None


class CameraNeighbor(Base):
    """Marca manual do dono da loja: 'essas duas câmeras cobrem áreas
    fisicamente adjacentes'. Usado pela correlação no edge (uma pessoa que
    some da câmera A e aparece na câmera B logo depois só é considerada a
    mesma se as duas forem vizinhas — evita correlacionar câmeras de
    pontas opostas da loja). Par não-ordenado: sempre armazenado com
    camera_id_a < camera_id_b (ver cameras.py) pra nunca duplicar (A,B) e
    (B,A) como linhas diferentes."""
    __tablename__ = "camera_neighbors"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    camera_id_a = Column(UUID(as_uuid=False), ForeignKey("cameras.id"), nullable=False)
    camera_id_b = Column(UUID(as_uuid=False), ForeignKey("cameras.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class SuppressedEvent(Base):
    """Log de auditoria: um comportamento suspeito que o correlator local
    da box (ver correlator.py no módulo de detecção) decidiu NÃO virar
    Alert, por considerar continuação de um evento recente numa câmera
    vizinha. Não é um Alert — de propósito, pra não duplicar o alerta que
    o correlator já está evitando — mas fica registrado pra o dono
    conseguir auditar se a supressão fez sentido (ex: duas pessoas
    diferentes com roupa parecida sendo tratadas como uma só)."""
    __tablename__ = "suppressed_events"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    store_id = Column(UUID(as_uuid=False), ForeignKey("stores.id"), nullable=False)
    camera_id = Column(UUID(as_uuid=False), ForeignKey("cameras.id"), nullable=False)
    matched_camera_id = Column(UUID(as_uuid=False), ForeignKey("cameras.id"), nullable=False)
    track_id = Column(Integer, nullable=False)
    confidence = Column(Float, nullable=False)
    appearance_distance = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


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


class PrepaidCheckout(Base):
    """Sessão de pagamento criada ANTES de existir empresa/usuário — o
    prospect paga primeiro, só depois cria a conta (ver prepaid_token em
    SignupIn). Não pertence a nenhuma empresa até ser reivindicado no
    cadastro (claimed_company_id), por isso não tem company_id — mesmo
    princípio do TeamInvite/PasswordResetToken: posse do claim_token é a
    credencial.

    Duas origens possíveis pro pagamento, mutuamente exclusivas (exatamente
    uma das duas fica preenchida):
      - asaas_checkout_id: Checkout hospedado pelo Asaas (fluxo de link de
        marketing, GET /v1/billing/prepaid-checkout) -- Asaas coleta nome/
        email/CPF na própria página dele, só recebemos o customer_id depois.
      - asaas_payment_id: cobrança Pix avulsa criada por nós mesmos (fluxo
        inline dentro do próprio cadastro, POST /v1/billing/prepaid-pix) --
        aqui SOMOS nós que chamamos create_customer, então já sabemos
        asaas_customer_id desde a criação, sem precisar descobrir depois.
    """
    __tablename__ = "prepaid_checkouts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    asaas_checkout_id = Column(String, nullable=True, unique=True)
    asaas_payment_id = Column(String, nullable=True, unique=True)
    claim_token = Column(String, nullable=False, unique=True)
    camera_packages = Column(Integer, nullable=False)
    monthly_value = Column(Float, nullable=False)
    # pending -> paid (webhook CHECKOUT_PAID ou PAYMENT_CONFIRMED/RECEIVED,
    # dependendo da origem) -> claimed (cadastro usou o token) | canceled | expired
    status = Column(String, nullable=False, default="pending")
    # No fluxo de checkout hospedado, só descoberto depois do pagamento
    # (ver AsaasClient.get_payments_for_checkout). No fluxo Pix inline, já
    # vem preenchido na criação (nós mesmos chamamos create_customer).
    asaas_customer_id = Column(String, nullable=True)
    asaas_subscription_id = Column(String, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    claimed_company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PendingStorePurchase(Base):
    """Loja adicional comprada por uma empresa JÁ existente (dono já
    logado, dashboard -> "Adicionar loja") — cada loja além da primeira é
    um pagamento avulso separado de PRICE_PER_PACKAGE (ver routers/
    billing.py), mesmo preço de um pacote de câmera, mas sem relação com
    limite de câmera nenhum.

    Mesmo princípio do PrepaidCheckout: nome/cidade digitados ficam
    guardados aqui até o pagamento confirmar (webhook) -- a Store de
    verdade (e a edge_api_key) só nascem depois, na primeira consulta de
    status autenticada depois da confirmação (ver store_purchase_status
    em routers/billing.py) -- é ali, não no webhook, que a api key em
    texto puro é gerada e devolvida, porque só existe uma sessão
    autenticada do dono nesse momento pra recebê-la com segurança."""
    __tablename__ = "pending_store_purchases"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id"), nullable=False)
    name = Column(String, nullable=False)
    city = Column(String, nullable=True)
    asaas_payment_id = Column(String, nullable=False, unique=True)
    # pending -> paid (webhook) -> claimed (store_purchase_status criou a
    # Store e devolveu a chave) | canceled | expired
    status = Column(String, nullable=False, default="pending")
    created_store_id = Column(UUID(as_uuid=False), ForeignKey("stores.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)


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
