"""
Armazenamento dos clipes de vídeo. Usa a API compatível com S3 — funciona
tanto com AWS S3 quanto com alternativas mais baratas (Cloudflare R2,
Backblaze B2), sem trocar código, só a configuração.
"""

import os
import uuid
import boto3
from botocore.client import Config

BUCKET_NAME = os.environ.get("CLIPS_BUCKET", "lossprevention-clips")


class ClipStorage:
    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,  # None = AWS padrão
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("S3_SECRET_KEY"),
            region_name="auto",
            # Cloudflare R2 só aceita URLs assinadas com SigV4 — sem isso o
            # boto3 cai pra SigV2 (legado) e a URL gerada dá 401 no R2.
            config=Config(signature_version="s3v4"),
        )

    def upload_clip(self, store_id: str, file_bytes: bytes, content_type: str) -> str:
        key = f"{store_id}/{uuid.uuid4()}.mp4"
        self.client.put_object(
            Bucket=BUCKET_NAME, Key=key, Body=file_bytes, ContentType=content_type
        )
        return self._public_or_signed_url(key)

    def upload_thumbnail(self, store_id: str, file_bytes: bytes) -> str:
        key = f"{store_id}/thumbs/{uuid.uuid4()}.jpg"
        self.client.put_object(
            Bucket=BUCKET_NAME, Key=key, Body=file_bytes, ContentType="image/jpeg"
        )
        return self._public_or_signed_url(key)

    def _public_or_signed_url(self, key: str) -> str:
        # Clipes contêm imagem de pessoas reais — em produção usar URL
        # assinada com expiração curta, não um bucket público.
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": key},
            ExpiresIn=3600,
        )
