import asyncio
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from job_crawler.config import CrawlConfig
from job_crawler.storage import Store, fingerprint
from job_crawler.transport import BrowserSession, CrawlError


class Page:
    def __init__(self, status: int = 200):
        self.calls = 0
        self.status = status
        self.scripts: list[str] = []

    async def evaluate(self, script: str) -> dict[str, Any]:
        self.calls += 1
        self.scripts.append(script)
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


async def test_form_post_is_encoded_and_cached_by_fields(tmp_path: Path, now: datetime) -> None:
    store = Store(tmp_path / "db.sqlite")
    store.begin("run", "hash", now, False, 6)
    session = BrowserSession(
        "A", "run", tmp_path / "evidence", store, CrawlConfig(delay=0), resume=True
    )
    page = Page()
    session.page = page
    try:
        await session.request("https://example.test/api", form={"postId": "a&b"}, detail=True)
        await session.request("https://example.test/api", form={"postId": "a&b"}, detail=True)
        await session.request("https://example.test/api", form={"postId": "other"}, detail=True)
        assert page.calls == 2
        assert "application/x-www-form-urlencoded" in page.scripts[0]
        assert "postId=a%26b" in page.scripts[0]
        with pytest.raises(ValueError, match="不能同时"):
            await session.request("https://example.test/api", payload={}, form={})
    finally:
        store.close()


async def test_server_rendered_form_keeps_html_evidence_and_detail_cache(
    tmp_path: Path, now: datetime
) -> None:
    store = Store(tmp_path / "db.sqlite")
    store.begin("run", "hash", now, False, 6)
    session = BrowserSession(
        "A", "run", tmp_path / "evidence", store, CrawlConfig(delay=0), resume=True
    )

    class HtmlPage(Page):
        async def evaluate(self, script: str) -> dict[str, Any]:
            self.calls += 1
            self.scripts.append(script)
            return {
                "status": 200,
                "body": "<html><body>岗位</body></html>",
                "url": "https://example.test/jobs",
            }

    page = HtmlPage()
    session.page = page
    try:
        first = await session.request_html(
            "https://example.test/jobs", form={"pagenum": "2&3"}, detail=True
        )
        again = await session.request_html(
            "https://example.test/jobs", form={"pagenum": "2&3"}, detail=True
        )
        assert first == again == "<html><body>岗位</body></html>"
        assert page.calls == 1
        assert "pagenum=2%263" in page.scripts[0]
        evidence = json.loads(await asyncio.to_thread(Path(session.last_evidence).read_text))
        assert evidence["html"] == first
    finally:
        store.close()


async def test_server_rendered_http_error_keeps_response_evidence(
    tmp_path: Path, now: datetime
) -> None:
    store = Store(tmp_path / "db.sqlite")
    store.begin("run", "hash", now, False, 6)
    session = BrowserSession(
        "A", "run", tmp_path / "evidence", store, CrawlConfig(delay=0, retries=0)
    )

    class DeniedPage(Page):
        async def evaluate(self, script: str) -> dict[str, Any]:
            return {"status": 403, "body": "访问受限", "url": "https://example.test/jobs"}

    session.page = DeniedPage()
    try:
        with pytest.raises(CrawlError, match="HTTP 403"):
            await session.request_html("https://example.test/jobs")
        evidence = json.loads(await asyncio.to_thread(Path(session.last_evidence).read_text))
        assert evidence["status"] == 403 and evidence["body"] == "访问受限"
    finally:
        store.close()


async def test_invalid_json_response_is_saved_as_evidence(tmp_path: Path, now: datetime) -> None:
    store = Store(tmp_path / "db.sqlite")
    store.begin("run", "hash", now, False, 6)
    session = BrowserSession(
        "A", "run", tmp_path / "evidence", store, CrawlConfig(delay=0, retries=0)
    )

    class EmptyResponsePage(Page):
        async def evaluate(self, script: str) -> dict[str, Any]:
            self.calls += 1
            return {"status": 200, "body": "", "url": "https://example.test/api"}

    session.page = EmptyResponsePage()
    try:
        with pytest.raises(CrawlError, match="不是 JSON"):
            await session.request("https://example.test/api")
        assert session.last_evidence
        evidence = json.loads(await asyncio.to_thread(Path(session.last_evidence).read_text))
        assert evidence["body"] == ""
        assert evidence["status"] == 200
    finally:
        store.close()


async def test_observed_path_ignores_similarly_named_api(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite")
    session = BrowserSession("A", "run", tmp_path / "evidence", store, CrawlConfig(delay=0))
    session.responses.extend(
        [
            {
                "url": "https://example.test/api/website/jobs/v2",
                "status": 200,
                "body": '{"jobs":[]}',
            },
            {
                "url": "https://example.test/api/website/jobs/v2/filterFieldsAggregations",
                "status": 200,
                "body": '{"filters":[]}',
            },
        ]
    )
    try:
        observed = await session.observed_path("/api/website/jobs/v2")
        assert observed["body"] == '{"jobs":[]}'
    finally:
        store.close()


def test_snapshot_preserves_tab_dom(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite")
    session = BrowserSession("A", "run", tmp_path / "evidence", store, CrawlConfig(delay=0))
    try:
        saved = session.snapshot("tab-02", "<div>second tab</div>")
        assert session.last_evidence == saved
        assert json.loads(Path(saved).read_text())["html"] == "<div>second tab</div>"
        with pytest.raises(ValueError):
            session.snapshot("../../outside", "")
    finally:
        store.close()


class NavigationPage:
    url = "https://example.test/jobs?type=campus"

    def __init__(self) -> None:
        self.handlers: dict[str, list[Callable[..., Any]]] = {}

    def on(self, event: str, callback: Callable[..., Any]) -> None:
        self.handlers.setdefault(event, []).append(callback)

    async def content(self) -> str:
        return "<html>jobs</html>"


@pytest.mark.parametrize(
    ("status", "body", "response_url", "page_url", "navigation_timeout", "recover"),
    [
        (
            412,
            '{"jobs": []}',
            "https://example.test/api/list?page=1",
            NavigationPage.url,
            False,
            True,
        ),
        (412, "not json", "https://example.test/api/list?page=1", NavigationPage.url, False, False),
        (412, '{"jobs": []}', "https://example.test/analytics", NavigationPage.url, False, False),
        (
            412,
            '{"jobs": []}',
            "https://other.test/api/list?page=1",
            NavigationPage.url,
            False,
            False,
        ),
        (
            412,
            '{"jobs": []}',
            "https://example.test/api/list?page=1",
            "https://other.test/jobs?type=campus",
            False,
            False,
        ),
        (
            412,
            '{"jobs": []}',
            "https://example.test/api/list?page=1",
            "https://example.test/jobs?type=social",
            False,
            False,
        ),
        (
            403,
            '{"jobs": []}',
            "https://example.test/api/list?page=1",
            NavigationPage.url,
            False,
            False,
        ),
        (
            200,
            '{"jobs": []}',
            "https://example.test/api/list?page=1",
            NavigationPage.url,
            True,
            True,
        ),
        (200, '{"jobs": []}', "https://example.test/analytics", NavigationPage.url, True, False),
    ],
)
async def test_entry_recovery_requires_current_business_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    body: str,
    response_url: str,
    page_url: str,
    navigation_timeout: bool,
    recover: bool,
) -> None:
    store = Store(tmp_path / "db.sqlite")
    session = BrowserSession("A", "run", tmp_path, store, CrawlConfig(delay=0, retries=0))
    page = NavigationPage()
    page.url = page_url
    session.page = page

    async def execute(*args: Any, **kwargs: Any) -> Any:
        session.responses.append({"url": response_url, "status": 200, "body": body})
        if navigation_timeout:
            raise CrawlError("browser_error", "Page.goto: Timeout while navigating")
        return SimpleNamespace(status_code=status, html="page")

    monkeypatch.setattr(session, "_execute", execute)
    try:
        if recover:
            await session.open(NavigationPage.url, ready_endpoints=("/api/list?",))
            assert session.url == NavigationPage.url
            assert session.navigation_warnings[0].code == "navigation_recovered"
            proof = json.loads(await asyncio.to_thread(Path(session.last_evidence).read_text))
            assert proof["readiness"][0]["url"] == response_url
        else:
            with pytest.raises(CrawlError):
                await session.open(NavigationPage.url, ready_endpoints=("/api/list?",))
            assert not session.navigation_warnings
    finally:
        store.close()


@pytest.mark.parametrize("endpoints", [(), ("/api/list?",), ("/api/list?", "/api/batches?")])
async def test_stale_or_partial_data_does_not_recover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, endpoints: tuple[str, ...]
) -> None:
    store = Store(tmp_path / "db.sqlite")
    session = BrowserSession("A", "run", tmp_path, store, CrawlConfig(delay=0, retries=0))
    session.page = NavigationPage()
    response = {"url": "https://example.test/api/list?page=1", "status": 200, "body": "{}"}
    session.responses.append(response)

    async def execute(*args: Any, **kwargs: Any) -> Any:
        if len(endpoints) == 2:
            session.responses.append(response)  # Only one of the two required endpoints arrived.
        return SimpleNamespace(status_code=412, html="page")

    monkeypatch.setattr(session, "_execute", execute)
    try:
        with pytest.raises(CrawlError, match="412"):
            await session.open(NavigationPage.url, ready_endpoints=endpoints)
        assert not session.navigation_warnings
    finally:
        store.close()


async def test_hooks_once_and_incomplete_body_still_records_failure(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite")
    session = BrowserSession("A", "run", tmp_path, store, CrawlConfig(delay=0))
    page = NavigationPage()

    class Request:
        url = "https://example.test/app.js"
        resource_type = "script"
        failure = "net::ERR_INCOMPLETE_CHUNKED_ENCODING"

    request = Request()
    try:
        await session._hook(page, None)
        await session._hook(page, None)
        assert all(len(handlers) == 1 for handlers in page.handlers.values())
        page.handlers["request"][0](request)
        page.handlers["response"][0](SimpleNamespace(request=request, status=200))
        page.handlers["requestfailed"][0](request)
        assert session.resource_failures[0]["error"] == request.failure
        page.handlers["request"][0](request)
        session.navigation_generation += 1
        page.handlers["requestfailed"][0](request)
        assert len(session.resource_failures) == 1
    finally:
        store.close()


async def test_delayed_response_from_previous_navigation_is_discarded(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite")
    session = BrowserSession("A", "run", tmp_path, store, CrawlConfig(delay=0))

    class Response:
        async def text(self) -> str:
            session.navigation_generation += 1
            return '{"jobs":[]}'

    try:
        await session._observe(Response(), session.navigation_generation)
        assert not session.responses
    finally:
        store.close()


async def test_navigation_and_script_use_separate_timeouts(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite")
    session = BrowserSession(
        "A",
        "run",
        tmp_path,
        store,
        CrawlConfig(delay=0, timeout=20, navigation_timeout=150),
    )
    timeouts = []

    class Crawler:
        async def arun(self, *, url: str, config: Any) -> Any:
            timeouts.append(config.page_timeout)
            return SimpleNamespace(success=True)

    session.crawler = Crawler()
    try:
        await session._execute(NavigationPage.url)
        await session._execute(NavigationPage.url, "void 0;")
        assert timeouts == [150000, 20000]
    finally:
        store.close()


async def test_structural_shell_requires_business_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path / "db.sqlite")
    session = BrowserSession("A", "run", tmp_path, store, CrawlConfig(delay=0, retries=0))
    session.page = NavigationPage()

    async def execute(*args: Any, **kwargs: Any) -> Any:
        session.responses.append(
            {"url": "https://example.test/api/List?page=1", "status": 200, "body": '{"Code":200}'}
        )
        raise CrawlError(
            "browser_error", "Blocked by anti-bot protection: Structural: minimal_text"
        )

    monkeypatch.setattr(session, "_execute", execute)
    try:
        await session.open(NavigationPage.url, ready_endpoints=("/api/list?",))
        assert session.navigation_warnings[0].code == "navigation_recovered"
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


async def test_public_language_header_is_preserved_and_cache_isolated(
    tmp_path: Path, now: datetime
) -> None:
    store = Store(tmp_path / "db.sqlite")
    store.begin("run", "hash", now, False, 6)
    session = BrowserSession(
        "A", "run", tmp_path / "evidence", store, CrawlConfig(delay=0), resume=True
    )
    page = Page()
    session.page = page
    try:
        for locale in ["zh_TW", "zh_TW", "en_US"]:
            await session.request(
                "https://example.test/detail", headers={"Accept-Language": locale}, detail=True
            )
        assert page.calls == 2
        assert '"Accept-Language": "zh_TW"' in page.scripts[0]
        assert '"Accept-Language": "en_US"' in page.scripts[1]
        with pytest.raises(ValueError, match="公开站点请求头"):
            await session.request("https://example.test/detail", headers={"Authorization": "test"})
    finally:
        store.close()
