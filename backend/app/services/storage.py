"""Pluggable file storage. Local disk by default; S3 interface stubbed.

The rest of the app depends only on the `Storage` protocol, so swapping to S3
(or GCS) is a config change, not a code change.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import settings


def make_key(organization_id: int, work_order_id: int, filename: str) -> str:
    """Deterministic-ish object key that keeps tenants and jobs partitioned."""
    safe = Path(filename).name.replace("/", "_")
    return f"{organization_id}/{work_order_id}/{uuid.uuid4().hex}_{safe}"


class Storage(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def load(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class LocalStorage(Storage):
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("Invalid storage key (path traversal).")
        return p

    def save(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def load(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()


class S3Storage(Storage):  # pragma: no cover - stub for production wiring
    """Placeholder. Wire boto3 here when SERVICEFLOW_STORAGE_BACKEND=s3."""

    def __init__(self, bucket: str, region: str) -> None:
        self.bucket = bucket
        self.region = region

    def _client(self):
        import boto3  # imported lazily so boto3 isn't a hard dependency in dev

        return boto3.client("s3", region_name=self.region)

    def save(self, key: str, data: bytes) -> None:
        self._client().put_object(Bucket=self.bucket, Key=key, Body=data)

    def load(self, key: str) -> bytes:
        return self._client().get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self._client().delete_object(Bucket=self.bucket, Key=key)


def get_storage() -> Storage:
    if settings.storage_backend == "s3" and settings.s3_bucket:
        return S3Storage(settings.s3_bucket, settings.s3_region)
    return LocalStorage(settings.storage_dir)


storage = get_storage()
