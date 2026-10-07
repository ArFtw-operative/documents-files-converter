import hashlib
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO

import boto3

from .config import settings


class Storage(ABC):
    @abstractmethod
    def put(self, key: str, stream: BinaryIO) -> tuple[int, str]: ...

    @abstractmethod
    def open(self, key: str) -> BinaryIO: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def copy_to(self, key: str, destination: Path) -> None: ...

    @abstractmethod
    def put_path(self, key: str, source: Path) -> tuple[int, str]: ...


class LocalStorage(Storage):
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        resolved = (self.root / key).resolve()
        if self.root not in resolved.parents:
            raise ValueError("Unsafe storage key")
        return resolved

    def put(self, key: str, stream: BinaryIO) -> tuple[int, str]:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest, size = hashlib.sha256(), 0
        with target.open("wb") as output:
            while chunk := stream.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
                if size > settings.max_upload_size:
                    output.close()
                    target.unlink(missing_ok=True)
                    raise ValueError("Upload exceeds configured size limit")
        return size, digest.hexdigest()

    def open(self, key: str) -> BinaryIO:
        return self.path(key).open("rb")

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def copy_to(self, key: str, destination: Path) -> None:
        shutil.copyfile(self.path(key), destination)

    def put_path(self, key: str, source: Path) -> tuple[int, str]:
        with source.open("rb") as stream:
            return self.put(key, stream)


class S3Storage(Storage):
    def __init__(self):
        self.client = boto3.client(
            "s3", endpoint_url=settings.s3_endpoint, aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key, region_name=settings.s3_region,
        )
        self.bucket = settings.s3_bucket

    def put(self, key: str, stream: BinaryIO) -> tuple[int, str]:
        digest, size = hashlib.sha256(), 0
        import tempfile
        with tempfile.TemporaryFile() as buffered:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_size:
                    raise ValueError("Upload exceeds configured size limit")
                digest.update(chunk); buffered.write(chunk)
            buffered.seek(0)
            self.client.upload_fileobj(buffered, self.bucket, key)
        return size, digest.hexdigest()

    def open(self, key: str) -> BinaryIO:
        import tempfile
        output = tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024)
        self.client.download_fileobj(self.bucket, key, output); output.seek(0)
        return output

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def copy_to(self, key: str, destination: Path) -> None:
        self.client.download_file(self.bucket, key, str(destination))

    def put_path(self, key: str, source: Path) -> tuple[int, str]:
        with source.open("rb") as stream:
            return self.put(key, stream)


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = S3Storage() if settings.storage_provider == "s3" else LocalStorage(settings.local_storage_path)
    return _storage


def safe_name(value: str) -> str:
    name = os.path.basename(value.replace("\\", "/"))
    clean = "".join(char if char.isalnum() or char in " ._-()" else "_" for char in name).strip(" .")
    return clean[:240] or "upload"
