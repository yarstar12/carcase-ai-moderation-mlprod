import importlib
from types import SimpleNamespace
from typing import Any

import pytest

from carcase_ai_moderation.infrastructure.s3_client import S3Client, S3Config, S3Error


class FakeClientError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeBotoCoreError(Exception):
    pass


def test_object_exists_false_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeS3:
        def head_object(self, *, Bucket: str, Key: str) -> None:
            _ = Bucket
            _ = Key
            raise FakeClientError("404")

        def put_object(self, **_kwargs: Any) -> None:
            raise AssertionError("not used")

    def fake_import(name: str) -> object:
        if name == "boto3":
            return SimpleNamespace(client=lambda *_args, **_kwargs: FakeS3())
        if name == "botocore.exceptions":
            return SimpleNamespace(ClientError=FakeClientError, BotoCoreError=FakeBotoCoreError)
        return importlib.import_module(name)

    monkeypatch.setattr(
        "carcase_ai_moderation.infrastructure.s3_client.importlib.import_module", fake_import
    )

    client = S3Client(S3Config(endpoint_url=None, access_key="a", secret_key="s", bucket="b"))
    assert client.object_exists(key="k") is False


def test_object_exists_raises_on_unknown_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeS3:
        def head_object(self, *, Bucket: str, Key: str) -> None:
            _ = Bucket
            _ = Key
            raise FakeClientError("500")

        def put_object(self, **_kwargs: Any) -> None:
            raise AssertionError("not used")

    def fake_import(name: str) -> object:
        if name == "boto3":
            return SimpleNamespace(client=lambda *_args, **_kwargs: FakeS3())
        if name == "botocore.exceptions":
            return SimpleNamespace(ClientError=FakeClientError, BotoCoreError=FakeBotoCoreError)
        return importlib.import_module(name)

    monkeypatch.setattr(
        "carcase_ai_moderation.infrastructure.s3_client.importlib.import_module", fake_import
    )

    client = S3Client(S3Config(endpoint_url=None, access_key="a", secret_key="s", bucket="b"))
    with pytest.raises(S3Error):
        client.object_exists(key="k")


def test_put_json_wraps_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeS3:
        def head_object(self, *, Bucket: str, Key: str) -> None:
            raise AssertionError("not used")

        def put_object(self, **_kwargs: Any) -> None:
            raise FakeClientError("500")

    def fake_import(name: str) -> object:
        if name == "boto3":
            return SimpleNamespace(client=lambda *_args, **_kwargs: FakeS3())
        if name == "botocore.exceptions":
            return SimpleNamespace(ClientError=FakeClientError, BotoCoreError=FakeBotoCoreError)
        return importlib.import_module(name)

    monkeypatch.setattr(
        "carcase_ai_moderation.infrastructure.s3_client.importlib.import_module", fake_import
    )

    client = S3Client(S3Config(endpoint_url=None, access_key="a", secret_key="s", bucket="b"))
    with pytest.raises(S3Error):
        client.put_json(key="k", payload={"x": 1})


def test_get_text_returns_object_body(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeBody:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def read(self) -> bytes:
            return self._data

    class FakeS3:
        def head_object(self, *, Bucket: str, Key: str) -> None:
            raise AssertionError("not used")

        def put_object(self, **_kwargs: Any) -> None:
            raise AssertionError("not used")

        def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
            _ = Bucket
            assert Key == "k"
            return {"Body": FakeBody(b"hello")}

    def fake_import(name: str) -> object:
        if name == "boto3":
            return SimpleNamespace(client=lambda *_args, **_kwargs: FakeS3())
        if name == "botocore.exceptions":
            return SimpleNamespace(ClientError=FakeClientError, BotoCoreError=FakeBotoCoreError)
        return importlib.import_module(name)

    monkeypatch.setattr(
        "carcase_ai_moderation.infrastructure.s3_client.importlib.import_module", fake_import
    )

    client = S3Client(S3Config(endpoint_url=None, access_key="a", secret_key="s", bucket="b"))
    assert client.get_text(key="k") == "hello"


def test_get_bytes_wraps_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeS3:
        def head_object(self, *, Bucket: str, Key: str) -> None:
            raise AssertionError("not used")

        def put_object(self, **_kwargs: Any) -> None:
            raise AssertionError("not used")

        def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
            _ = Bucket
            _ = Key
            raise FakeClientError("500")

    def fake_import(name: str) -> object:
        if name == "boto3":
            return SimpleNamespace(client=lambda *_args, **_kwargs: FakeS3())
        if name == "botocore.exceptions":
            return SimpleNamespace(ClientError=FakeClientError, BotoCoreError=FakeBotoCoreError)
        return importlib.import_module(name)

    monkeypatch.setattr(
        "carcase_ai_moderation.infrastructure.s3_client.importlib.import_module", fake_import
    )

    client = S3Client(S3Config(endpoint_url=None, access_key="a", secret_key="s", bucket="b"))
    with pytest.raises(S3Error):
        client.get_bytes(key="k")
