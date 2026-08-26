from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator


def _normalize_email(value: str) -> str:
    # Sem isso, "Nome@Gmail.com" e "nome@gmail.com" viram contas diferentes
    # aos olhos do banco — cadastro duplicado sem querer, ou login que
    # falha só porque a pessoa digitou com letra maiúscula.
    return value.strip().lower()


class AlertOut(BaseModel):
    id: str
    store_id: str
    camera_label: str
    confidence: float
    reason: str
    clip_url: str
    thumbnail_url: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class AlertReviewIn(BaseModel):
    status: str  # "confirmed" ou "dismissed" — validado no router


class StoreOut(BaseModel):
    id: str
    name: str
    city: Optional[str]
    onboarding_status: str
    last_seen_at: Optional[datetime]
    online: bool

    class Config:
        from_attributes = True


class StoreCreateIn(BaseModel):
    name: str
    city: Optional[str] = None


class EdgeWhoamiOut(BaseModel):
    store_id: str
    store_name: str


class StoreCreateOut(BaseModel):
    id: str
    name: str
    city: Optional[str]
    edge_api_key: str

    class Config:
        from_attributes = True


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    turnstile_token: str

    _normalize_email = field_validator("email")(_normalize_email)


class SignupIn(BaseModel):
    company_name: str
    store_name: str
    store_city: Optional[str] = None
    owner_name: str
    email: EmailStr
    password: str
    turnstile_token: str
    # Presente quando o cadastro vem do fluxo de aquisição por link de
    # marketing (pagou antes de ter conta) — ver GET /v1/billing/
    # prepaid-checkout e PrepaidCheckout em models.py.
    prepaid_token: Optional[str] = None

    _normalize_email = field_validator("email")(_normalize_email)


class ForgotPasswordIn(BaseModel):
    email: EmailStr
    # "dashboard" ou "admin" — decide se o link do email aponta pro painel
    # do cliente ou pro painel administrativo interno (mesma tabela de
    # usuários serve os dois, mas os painéis são apps/domínios diferentes).
    app: str = "dashboard"
    turnstile_token: str

    _normalize_email = field_validator("email")(_normalize_email)


class ForgotPasswordOut(BaseModel):
    detail: str


class ResetPasswordIn(BaseModel):
    token: str
    password: str


class SignupOut(BaseModel):
    store_id: str
    store_edge_api_key: str


class TeamInviteIn(BaseModel):
    name: str
    email: EmailStr
    store_ids: list[str]  # lojas às quais este gestor terá acesso

    _normalize_email = field_validator("email")(_normalize_email)


class TeamInviteOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    status: str = "sent"  # o email já foi disparado nesta chamada


class InviteDetailsOut(BaseModel):
    name: str
    email: EmailStr
    company_name: str
    store_names: list[str]


class InviteAcceptIn(BaseModel):
    password: str


class TeamMemberOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: str
    store_ids: list[str]
    status: str = "active"  # "active" ou "pending" (convite ainda não aceito)

    class Config:
        from_attributes = True


class MeOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: str
    is_platform_admin: bool
    access_paused: bool


class AdminCompanyOut(BaseModel):
    id: str
    name: str
    created_at: str
    store_count: int
    user_count: int
    subscription_status: str
    camera_limit: int
    cameras_used: int
    access_paused: bool


class AdminCompanyDetailOut(BaseModel):
    id: str
    name: str
    created_at: str
    subscription_status: str
    camera_limit: int
    cameras_used: int
    access_paused: bool
    stores: list[StoreOut]
    users: list[TeamMemberOut]


class AdminOnboardingOut(BaseModel):
    store_id: str
    store_name: str
    company_id: str
    company_name: str
    payment_confirmed_at: Optional[str]
    onboarding_status: str
    online: bool
    last_seen_at: Optional[str]


class OnboardingStatusIn(BaseModel):
    status: str  # "pending" | "in_progress" | "completed" — validado no router


class AdminDeleteCompanyIn(BaseModel):
    # Senha do PRÓPRIO admin logado (re-autenticação pra confirmar uma
    # ação irreversível) -- não é a senha de ninguém da empresa sendo
    # excluída, ver delete_company em routers/admin.py.
    password: str


class AdminCameraAlertsOut(BaseModel):
    # Contexto pra calibrar com dado, não às cegas (ver
    # get_camera_alerts_admin em routers/admin.py): últimas detecções +
    # contadores por período. O preview de imagem no admin reaproveita o
    # thumbnail_url do primeiro item de `alerts` (mais recente) -- não é
    # um snapshot dedicado, é aproximação de propósito por enquanto.
    alerts: list[AlertOut]
    count_24h: int
    count_7d: int


class CameraOut(BaseModel):
    id: str
    store_id: str
    label: str
    active: bool
    zone_of_interest: Optional[list] = None
    hand_still_frames_threshold: Optional[int] = None
    min_confidence_to_alert: Optional[float] = None
    calibration_updated_at: Optional[datetime] = None
    calibration_updated_by_name: Optional[str] = None

    class Config:
        from_attributes = True


class CameraCreateIn(BaseModel):
    label: str


def _validate_zone_of_interest(value: Optional[list]) -> Optional[list]:
    # Mesma convenção usada há tempos em config.py (edge-detection):
    # vazio/None = sem zona configurada, zona vira o quadro inteiro. Um
    # polígono de verdade precisa de pelo menos 3 pontos, cada um um par
    # [x, y] normalizado (0-1) -- é isso que vira Polygon() do lado da
    # box (pose_rules.py); um valor fora desse formato quebraria a
    # aplicação da calibração no processo de detecção, não só um erro de
    # UI, por isso a validação aqui é rígida.
    if value is None or value == []:
        return value
    if not isinstance(value, list) or len(value) < 3:
        raise ValueError("Zona de interesse precisa ter pelo menos 3 pontos, ou ficar vazia")
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError("Cada ponto da zona precisa ser um par [x, y]")
        x, y = point
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not (0 <= x <= 1) or not (0 <= y <= 1):
            raise ValueError("Coordenadas da zona precisam estar entre 0 e 1")
    return value


class CameraCalibrationOut(BaseModel):
    """Retorno enxuto pra BOX (GET .../calibration) -- só o que
    calibration_sync.py precisa pra decidir se mudou algo e aplicar.
    Não expõe label/active de propósito, pra manter o contrato com a
    box o mais estreito possível."""
    camera_id: str
    zone_of_interest: Optional[list] = None
    hand_still_frames_threshold: Optional[int] = None
    min_confidence_to_alert: Optional[float] = None
    updated_at: Optional[datetime] = None


class CameraCalibrationUpdateIn(BaseModel):
    # Todos opcionais -- PATCH parcial, tanto o dono (dashboard) quanto o
    # admin (painel interno, durante o piloto) podem mandar só o campo
    # que estão ajustando.
    zone_of_interest: Optional[list] = None
    hand_still_frames_threshold: Optional[int] = None
    min_confidence_to_alert: Optional[float] = None

    _validate_zone = field_validator("zone_of_interest")(_validate_zone_of_interest)

    @field_validator("hand_still_frames_threshold")
    @classmethod
    def _validate_threshold(cls, value):
        if value is not None and value <= 0:
            raise ValueError("hand_still_frames_threshold precisa ser maior que zero")
        return value

    @field_validator("min_confidence_to_alert")
    @classmethod
    def _validate_confidence(cls, value):
        if value is not None and not (0 < value <= 1):
            raise ValueError("min_confidence_to_alert precisa estar entre 0 (exclusivo) e 1")
        return value


class CameraNeighborOut(BaseModel):
    id: str
    camera_id_a: str
    camera_id_b: str

    class Config:
        from_attributes = True


class CameraNeighborCreateIn(BaseModel):
    camera_id_a: str
    camera_id_b: str


class SuppressedEventIn(BaseModel):
    camera_id: str
    matched_camera_id: str
    track_id: int
    confidence: float
    appearance_distance: float


class SuppressedEventOut(BaseModel):
    id: str
    camera_id: str
    camera_label: str
    matched_camera_id: str
    matched_camera_label: str
    track_id: int
    confidence: float
    appearance_distance: float
    created_at: datetime


class SubscribeIn(BaseModel):
    cpf_cnpj: str          # CPF ou CNPJ do responsável/empresa, exigido pelo Asaas
    camera_packages: int    # quantidade de pacotes de câmeras (ver CAMERAS_PER_PACKAGE em routers/billing.py; mínimo 1)


class SubscribeOut(BaseModel):
    subscription_status: str
    camera_limit_pending: int      # quantas câmeras ficarão liberadas quando o pagamento confirmar
    monthly_value: float
    pix_qr_code_image: str | None = None   # base64, para renderizar a imagem do QR Code
    pix_copy_paste: str | None = None       # código "copia e cola"
    pix_expiration: str | None = None


class BillingStatusOut(BaseModel):
    subscription_status: str
    camera_limit: int
    cameras_used: int


class PrepaidPixIn(BaseModel):
    # Coletado ANTES do nome do negócio/loja de propósito (ver POST
    # /v1/billing/prepaid-pix) -- é o mínimo que o Asaas exige pra criar
    # um cliente e gerar uma cobrança Pix (create_customer), então tem
    # que vir primeiro nessa variante inline (diferente do Checkout
    # hospedado, onde é o próprio Asaas que coleta isso na página dele).
    owner_name: str
    email: EmailStr
    cpf_cnpj: str
    camera_packages: int

    _normalize_email = field_validator("email")(_normalize_email)


class PrepaidPixOut(BaseModel):
    claim_token: str
    monthly_value: float
    pix_qr_code_image: str | None = None
    pix_copy_paste: str | None = None
    pix_expiration: str | None = None


class PrepaidPixStatusOut(BaseModel):
    status: str  # pending | paid | claimed | canceled | expired


class StorePurchaseIn(BaseModel):
    name: str
    city: Optional[str] = None
    # Só é exigido se a empresa ainda não tem asaas_customer_id (nunca
    # assinou antes) -- ver purchase_store em routers/billing.py.
    cpf_cnpj: Optional[str] = None


class StorePurchaseOut(BaseModel):
    id: str  # id do PendingStorePurchase, usado pro polling de status
    monthly_value: float
    pix_qr_code_image: str | None = None
    pix_copy_paste: str | None = None
    pix_expiration: str | None = None


class StorePurchaseStatusOut(BaseModel):
    status: str  # pending | paid | claimed
    store: Optional[StoreCreateOut] = None  # só vem preenchido na PRIMEIRA consulta depois de "paid" -- a chave é mostrada uma única vez
