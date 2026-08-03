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

    class Config:
        from_attributes = True


class StoreCreateIn(BaseModel):
    name: str
    city: Optional[str] = None


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

    _normalize_email = field_validator("email")(_normalize_email)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SignupOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
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


class AdminCompanyOut(BaseModel):
    id: str
    name: str
    created_at: str
    store_count: int
    user_count: int
    subscription_status: str


class AdminCompanyDetailOut(BaseModel):
    id: str
    name: str
    created_at: str
    subscription_status: str
    stores: list[StoreOut]
    users: list[TeamMemberOut]


class SubscribeIn(BaseModel):
    cpf_cnpj: str        # CPF ou CNPJ do responsável/empresa, exigido pelo Asaas
    plan_value: float     # valor mensal da assinatura, em reais


class SubscribeOut(BaseModel):
    subscription_status: str
    pix_qr_code_image: str | None = None   # base64, para renderizar a imagem do QR Code
    pix_copy_paste: str | None = None       # código "copia e cola"
    pix_expiration: str | None = None


class BillingStatusOut(BaseModel):
    subscription_status: str
