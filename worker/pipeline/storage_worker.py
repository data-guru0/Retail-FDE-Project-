"""Worker-side MinIO reads: fetch the product reference image and the return photo
for a given return."""
from __future__ import annotations

import boto3
from botocore.client import Config as BotoConfig

from pipeline import db
from pipeline.settings import get_settings

_cfg = BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"})


def _s3(endpoint: str | None = None):
    s = get_settings()
    return boto3.client(
        "s3", endpoint_url=endpoint or s.minio_endpoint,
        aws_access_key_id=s.minio_access_key, aws_secret_access_key=s.minio_secret_key,
        config=_cfg, region_name="auto",
    )


def _get(key: str) -> bytes | None:
    try:
        return _s3().get_object(Bucket=get_settings().minio_bucket, Key=key)["Body"].read()
    except Exception:  # noqa: BLE001
        return None


async def _product_key(return_id: str) -> str | None:
    row = await db.fetchrow(
        "SELECT p.image_key FROM returns r "
        "JOIN order_items oi ON oi.id = r.order_item_id "
        "JOIN products p ON p.id = oi.product_id WHERE r.id = %(r)s",
        {"r": return_id},
    )
    return row["image_key"] if row else None


async def _photo_key(return_id: str) -> str | None:
    row = await db.fetchrow(
        "SELECT object_key FROM return_photos WHERE return_id = %(r)s ORDER BY created_at LIMIT 1",
        {"r": return_id},
    )
    return row["object_key"] if row else None


async def product_image_bytes(return_id: str) -> bytes | None:
    k = await _product_key(return_id)
    return _get(k) if k else None


async def return_photo_bytes(return_id: str) -> bytes | None:
    k = await _photo_key(return_id)
    return _get(k) if k else None


async def return_photo_url(return_id: str) -> str | None:
    k = await _photo_key(return_id)
    if not k:
        return None
    return _s3("http://localhost:9000").generate_presigned_url(
        "get_object", Params={"Bucket": get_settings().minio_bucket, "Key": k}, ExpiresIn=600
    )
