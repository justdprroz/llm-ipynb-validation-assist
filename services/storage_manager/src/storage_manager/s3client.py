from __future__ import annotations

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from storage_manager.config import Settings


def make_client(settings: Settings) -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )


def ensure_buckets(client: BaseClient, buckets: list[str]) -> None:
    existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    for name in buckets:
        if name not in existing:
            client.create_bucket(Bucket=name)


def head_object_exists(client: BaseClient, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "404":
            return False
        raise


def put_bytes(client: BaseClient, bucket: str, key: str, data: bytes, content_type: str | None = None) -> None:
    kwargs: dict = {"Bucket": bucket, "Key": key, "Body": data}
    if content_type:
        kwargs["ContentType"] = content_type
    client.put_object(**kwargs)


def get_bytes(client: BaseClient, bucket: str, key: str) -> bytes:
    obj = client.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read()


def list_keys(client: BaseClient, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    token: str | None = None
    while True:
        kwargs: dict = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        keys.extend(o["Key"] for o in resp.get("Contents", []))
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return keys


def delete_prefix(client: BaseClient, bucket: str, prefix: str) -> None:
    for key in list_keys(client, bucket, prefix):
        client.delete_object(Bucket=bucket, Key=key)
