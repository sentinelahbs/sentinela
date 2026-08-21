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

    def delete_store_clips(self, store_id: str) -> None:
        """Apaga todos os clipes e thumbnails de uma loja (chave sempre
        prefixada por "{store_id}/", ver upload_clip/upload_thumbnail
        acima) -- usado na exclusão real de empresa pelo painel admin,
        pra não deixar vídeo de pessoa real órfão no bucket pra sempre.
        Paginado porque uma loja com meses de histórico pode passar dos
        1000 objetos que list_objects_v2 devolve por página."""
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=f"{store_id}/"):
            keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if keys:
                self.client.delete_objects(Bucket=BUCKET_NAME, Delete={"Objects": keys})

    def _public_or_signed_url(self, key: str) -> str:
        # Clipes contêm imagem de pessoas reais — em produção usar URL
        # assinada com expiração curta, não um bucket público.
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": key},
            ExpiresIn=3600,
        )
