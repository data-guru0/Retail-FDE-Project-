"""MinIO (S3) object storage — real puts, real presigned GETs.

Two clients: the internal one (docker network) does puts/heads; the public one is
only ever used to *compute* presigned URLs (no network call) so the SigV4 host in
the signature matches what the browser will actually connect to.
"""
from __future__ import annotations

import boto3
from botocore.client import Config as BotoConfig

from app.settings import get_settings

_PUBLIC_ENDPOINT = "http://localhost:9000"
_cfg = BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"})


def _client(endpoint: str | None = None):
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=endpoint or s.minio_endpoint,
        aws_access_key_id=s.minio_access_key,
        aws_secret_access_key=s.minio_secret_key,
        config=_cfg,
        region_name="auto",
    )


def put_bytes(key: str, data: bytes, content_type: str) -> None:
    _client().put_object(
        Bucket=get_settings().minio_bucket, Key=key, Body=data, ContentType=content_type
    )


def presigned_get(key: str, expires: int = 3600) -> str:
    return _client(_PUBLIC_ENDPOINT).generate_presigned_url(
        "get_object",
        Params={"Bucket": get_settings().minio_bucket, "Key": key},
        ExpiresIn=expires,
    )


def exists(key: str) -> bool:
    try:
        _client().head_object(Bucket=get_settings().minio_bucket, Key=key)
        return True
    except Exception:
        return False
