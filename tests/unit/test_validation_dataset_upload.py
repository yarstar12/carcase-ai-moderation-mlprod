from __future__ import annotations

from pathlib import Path

import pytest

from carcase_ai_moderation.batch import validation_dataset_upload


def test_require_env_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("S3_BUCKET", raising=False)
    with pytest.raises(validation_dataset_upload.BatchError):
        validation_dataset_upload._require_env("S3_BUCKET")


def test_main_raises_on_missing_dataset_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"
    with pytest.raises(validation_dataset_upload.BatchError, match="dataset-path does not exist"):
        validation_dataset_upload.main(["--dataset-path", str(missing)])


def test_main_raises_on_directory_dataset_path(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset_dir"
    dataset_dir.mkdir()
    with pytest.raises(validation_dataset_upload.BatchError, match="dataset-path must be a file"):
        validation_dataset_upload.main(["--dataset-path", str(dataset_dir)])


def test_main_raises_on_empty_dataset_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(validation_dataset_upload.BatchError, match="dataset-path is empty"):
        validation_dataset_upload.main(["--dataset-path", str(empty)])


def test_main_skips_upload_when_object_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text('{"x":1}\n', encoding="utf-8")

    monkeypatch.setenv("S3_ACCESS_KEY", "a")
    monkeypatch.setenv("S3_SECRET_KEY", "s")
    monkeypatch.setenv("S3_BUCKET", "bucket")

    calls: dict[str, list[object]] = {"object_exists": [], "put_bytes": []}

    def fake_object_exists(self: object, *, key: str) -> bool:
        calls["object_exists"].append(key)
        return True

    def fake_put_bytes(
        self: object, *, key: str, body: bytes, content_type: str | None = None
    ) -> None:
        calls["put_bytes"].append((key, body, content_type))

    monkeypatch.setattr(validation_dataset_upload.S3Client, "object_exists", fake_object_exists)
    monkeypatch.setattr(validation_dataset_upload.S3Client, "put_bytes", fake_put_bytes)

    code = validation_dataset_upload.main(
        [
            "--dataset-version",
            "v1",
            "--dataset-kind",
            "smoke",
            "--datasets-prefix",
            "datasets/validation",
            "--dataset-path",
            str(dataset),
        ]
    )
    assert code == 0
    assert calls["object_exists"] == ["datasets/validation/v1.smoke.jsonl"]
    assert calls["put_bytes"] == []


def test_main_uploads_when_object_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    body = b'{"x":1}\n{"x":2}\n'
    dataset.write_bytes(body)

    monkeypatch.setenv("S3_ACCESS_KEY", "a")
    monkeypatch.setenv("S3_SECRET_KEY", "s")
    monkeypatch.setenv("S3_BUCKET", "bucket")

    calls: dict[str, list[object]] = {"object_exists": [], "put_bytes": []}

    def fake_object_exists(self: object, *, key: str) -> bool:
        calls["object_exists"].append(key)
        return False

    def fake_put_bytes(
        self: object, *, key: str, body: bytes, content_type: str | None = None
    ) -> None:
        calls["put_bytes"].append((key, body, content_type))

    monkeypatch.setattr(validation_dataset_upload.S3Client, "object_exists", fake_object_exists)
    monkeypatch.setattr(validation_dataset_upload.S3Client, "put_bytes", fake_put_bytes)

    code = validation_dataset_upload.main(
        [
            "--dataset-version",
            "v1",
            "--dataset-kind",
            "full",
            "--datasets-prefix",
            "datasets/validation",
            "--dataset-path",
            str(dataset),
        ]
    )
    assert code == 0
    assert calls["object_exists"] == ["datasets/validation/v1.jsonl"]
    assert calls["put_bytes"] == [("datasets/validation/v1.jsonl", body, "application/x-ndjson")]


def test_main_overwrites_when_requested(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text('{"x":1}\n', encoding="utf-8")

    monkeypatch.setenv("S3_ACCESS_KEY", "a")
    monkeypatch.setenv("S3_SECRET_KEY", "s")
    monkeypatch.setenv("S3_BUCKET", "bucket")

    calls: dict[str, list[object]] = {"object_exists": [], "put_bytes": []}

    def fake_object_exists(self: object, *, key: str) -> bool:
        calls["object_exists"].append(key)
        return True

    def fake_put_bytes(
        self: object, *, key: str, body: bytes, content_type: str | None = None
    ) -> None:
        calls["put_bytes"].append((key, body, content_type))

    monkeypatch.setattr(validation_dataset_upload.S3Client, "object_exists", fake_object_exists)
    monkeypatch.setattr(validation_dataset_upload.S3Client, "put_bytes", fake_put_bytes)

    code = validation_dataset_upload.main(
        [
            "--dataset-version",
            "v1",
            "--dataset-kind",
            "smoke",
            "--datasets-prefix",
            "datasets/validation",
            "--dataset-path",
            str(dataset),
            "--overwrite",
        ]
    )
    assert code == 0
    assert calls["object_exists"] == []
    assert len(calls["put_bytes"]) == 1
