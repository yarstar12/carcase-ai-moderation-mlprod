from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from typing import Any, cast


class S3Error(RuntimeError):
    pass


def _import_boto3() -> tuple[Any, Any]:
    try:
        boto3 = importlib.import_module("boto3")
        botocore_exceptions = importlib.import_module("botocore.exceptions")
        return boto3, botocore_exceptions
    except ModuleNotFoundError as exc:
        raise S3Error("boto3 is required for S3 client") from exc


@dataclass(frozen=True, slots=True)
class S3Config:
    endpoint_url: str | None
    access_key: str
    secret_key: str
    bucket: str
    region: str = "us-east-1"


@dataclass(frozen=True, slots=True)
class S3Client:
    config: S3Config

    def _client(self) -> Any:
        boto3, _ = _import_boto3()
        return boto3.client(
            "s3",
            endpoint_url=self.config.endpoint_url,
            aws_access_key_id=self.config.access_key,
            aws_secret_access_key=self.config.secret_key,
            region_name=self.config.region,
        )

    def object_exists(self, *, key: str) -> bool:
        _, botocore_exceptions = _import_boto3()
        client_error = cast(type[BaseException], botocore_exceptions.ClientError)

        client = self._client()
        try:
            client.head_object(Bucket=self.config.bucket, Key=key)
        except client_error as exc:
            response = getattr(exc, "response", {})
            error = response.get("Error", {}) if isinstance(response, dict) else {}
            code = error.get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise S3Error("S3 head_object failed") from exc
        return True

    def put_json(self, *, key: str, payload: dict[str, object]) -> None:
        _, botocore_exceptions = _import_boto3()
        client_error = cast(type[BaseException], botocore_exceptions.ClientError)
        botocore_error = cast(type[BaseException], botocore_exceptions.BotoCoreError)

        client = self._client()
        body = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        try:
            client.put_object(
                Bucket=self.config.bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
            )
        except (client_error, botocore_error) as exc:
            raise S3Error("S3 put_object failed") from exc

    def get_bytes(self, *, key: str) -> bytes:
        _, botocore_exceptions = _import_boto3()
        client_error = cast(type[BaseException], botocore_exceptions.ClientError)
        botocore_error = cast(type[BaseException], botocore_exceptions.BotoCoreError)

        client = self._client()
        try:
            response = client.get_object(Bucket=self.config.bucket, Key=key)
        except (client_error, botocore_error) as exc:
            raise S3Error("S3 get_object failed") from exc

        body = response.get("Body")
        if body is None:
            raise S3Error("S3 get_object returned empty Body")

        try:
            data_obj: object = body.read()
        except (OSError, botocore_error) as exc:
            raise S3Error("Failed to read S3 object body") from exc
        if isinstance(data_obj, bytes):
            return data_obj
        if isinstance(data_obj, bytearray):
            return bytes(data_obj)
        raise S3Error("S3 get_object Body.read() returned non-bytes")

    def get_text(self, *, key: str, encoding: str = "utf-8") -> str:
        return self.get_bytes(key=key).decode(encoding)
