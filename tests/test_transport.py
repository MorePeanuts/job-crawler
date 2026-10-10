import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from job_crawler.config import CrawlConfig
from job_crawler.storage import Store, fingerprint
from job_crawler.transport import BrowserSession, CrawlError


class Page:
    def __init__(self, status: int = 200):
        self.calls = 0
        self.status = status

    async def evaluate(self, script: str) -> dict[str, Any]:
        self.calls += 1
        return {"status": self.status, "body": '{"value":1}', "url": "https://example.test/api"}


async def test_only_successful_details_are_reused(tmp_path: Path, now: datetime) -> None:
    store = Store(tmp_path / "db.sqlite")
    store.begin("run", "hash", now, False, 6)
    session = BrowserSession(
        "A", "run", tmp_path / "evidence", store, CrawlConfig(delay=0), resume=True
    )
    page = Page()
    session.page = page
    try:
        await session.request("https://example.test/detail", detail=True)
        await session.request("https://example.test/detail", detail=True)
        assert page.calls == 1
        await session.request("https://example.test/list")
        await session.request("https://example.test/list")
        assert page.calls == 3
        # A new detail payload must not reuse another job's cached response.
        await session.request("https://example.test/detail", payload={"id": "other"}, detail=True)
        assert page.calls == 4
    finally:
        store.close()


async def test_access_denied_no_retries_and_keeps_evidence(tmp_path: Path, now: datetime) -> None:
    store = Store(tmp_path / "db.sqlite")
    store.begin("run", "hash", now, False, 6)
    session = BrowserSession(
        "A", "run", tmp_path / "evidence", store, CrawlConfig(delay=0, retries=3)
    )
    page = Page(403)
    session.page = page
    try:
        with pytest.raises(CrawlError, match="403"):
            await session.request("https://example.test/api")
        assert page.calls == 1
        saved = list((tmp_path / "evidence").glob("*.json"))
        assert len(saved) == 1 and json.loads(saved[0].read_text())["status"] == 403
        key = fingerprint({"url": "https://example.test/api", "payload": None})
        assert store.cached("run", "A", key) is None
    finally:
        store.close()


async def test_budget_stops_before_sending_request(tmp_path: Path, now: datetime) -> None:
    store = Store(tmp_path / "db.sqlite")
    store.begin("run", "hash", now, False, 6)
    session = BrowserSession(
        "A", "run", tmp_path / "evidence", store, CrawlConfig(delay=0, max_requests=1)
    )
    page = Page()
    session.page = page
    try:
        await session.request("https://example.test/api")
        with pytest.raises(CrawlError, match="预算"):
            await session.request("https://example.test/api2")
        assert page.calls == 1
    finally:
        store.close()
