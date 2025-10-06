from pathlib import Path
from typing import Iterator

import pytest

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import main


class DummyResponse:
    def __init__(
        self,
        chunks: Iterator[bytes],
        raise_exc: Exception | None = None,
        iter_exception: Exception | None = None,
    ):
        self._chunks = list(chunks)
        self._raise_exc = raise_exc
        self._iter_exception = iter_exception

    def __enter__(self):
        if self._raise_exc:
            raise self._raise_exc
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc

    def iter_content(self, chunk_size: int):
        for chunk in self._chunks:
            yield chunk
        if self._iter_exception:
            raise self._iter_exception


class DummySession:
    def __init__(self, response: DummyResponse):
        self._response = response

    def get(self, url: str, stream: bool, timeout: int):
        return self._response


def test_create_requests_session_has_retry_configuration():
    session = main._create_requests_session()

    assert session.adapters["https://"].max_retries.total == 3
    assert session.adapters["https://"].max_retries.backoff_factor == 1.5
    assert session.headers["User-Agent"].startswith("Mozilla/5.0")


def test_download_pdf_skips_when_file_exists(tmp_path, monkeypatch):
    target = tmp_path / "existing.pdf"
    target.write_text("original")

    def fail_session():  # pragma: no cover - defensive guard
        raise AssertionError("Session should not be created when file exists")

    monkeypatch.setattr(main, "_create_requests_session", fail_session)

    main.download_pdf("http://example.com/file", str(tmp_path), "existing")

    assert target.read_text() == "original"


def test_download_pdf_streams_content(tmp_path, monkeypatch):
    response = DummyResponse(iter([b"chunk1", b"chunk2"]))
    monkeypatch.setattr(main, "_create_requests_session", lambda: DummySession(response))

    main.download_pdf("http://example.com/file", str(tmp_path), "resource")

    written = (tmp_path / "resource.pdf").read_bytes()
    assert written == b"chunk1chunk2"


def test_download_pdf_removes_partial_file_on_failure(tmp_path, monkeypatch):
    target_path = tmp_path / "broken.pdf"

    response = DummyResponse(
        iter([b"partial"]),
        iter_exception=main.RequestException("boom"),
    )
    monkeypatch.setattr(main, "_create_requests_session", lambda: DummySession(response))

    main.download_pdf("http://example.com/file", str(tmp_path), "broken")

    assert not target_path.exists()


def test_chunked_yields_even_and_final_chunks():
    data = list(range(7))
    chunks = list(main._chunked(data, 3))

    assert chunks == [[0, 1, 2], [3, 4, 5], [6]]


class _Result:
    def get(self):
        return None


class _Pool:
    def __init__(self, processes: int):
        self.processes = processes

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def apply_async(self, func, args):
        func(*args)
        return _Result()


class _Tqdm:
    def __init__(self, *args, **kwargs):
        self.total = kwargs.get("total")
        self.desc = kwargs.get("desc")
        self.updated = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def update(self, amount: int):
        self.updated += amount


def test_download_issuu_pdfs_deduplicates_and_tracks_progress(monkeypatch):
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(main.multiprocessing, "Pool", _Pool)
    monkeypatch.setattr(main.multiprocessing, "cpu_count", lambda: 4)
    monkeypatch.setattr(main, "download_link_pdf", lambda link, folder: calls.append((link, folder)))
    monkeypatch.setattr(main, "tqdm", lambda *args, **kwargs: _Tqdm(*args, **kwargs))

    links = ["a", "b", "a", "c"]
    main.download_issuu_pdfs(links, "folder")

    assert calls == [("a", "folder"), ("b", "folder"), ("c", "folder")]
