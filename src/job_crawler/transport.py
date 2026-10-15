"""Crawl4AI browser and API execution with bounded evidence capture."""

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlencode, urlsplit

from job_crawler.config import CrawlConfig
from job_crawler.models import Issue
from job_crawler.retention import evidence_exists, read_evidence
from job_crawler.storage import Store, fingerprint, write_json


class CrawlError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Session(Protocol):
    last_evidence: str

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None: ...
    async def observed(self, needle: str) -> dict[str, Any]: ...
    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]: ...


class BrowserSession:
    def __init__(
        self,
        source_id: str,
        run_id: str,
        output: Path,
        store: Store,
        config: CrawlConfig,
        resume: bool = False,
    ):
        self.source_id = source_id
        self.run_id = run_id
        self.output = output
        self.store = store
        self.config = config
        self.resume = resume
        self.url = ""
        self.last_evidence = ""
        self.requests = 0
        self.crawler: Any = None  # Crawl4AI's dynamic hook/union return boundary.
        self.page: Any = None  # Page supplied by the Crawl4AI hook; shares its browser/cookies.
        self.responses: list[dict[str, Any]] = []
        self.pending: set[asyncio.Task[None]] = set()
        self.capture = True
        self.started = time.monotonic()
        self.resource_failures: list[dict[str, Any]] = []
        self.navigation_warnings: list[Issue] = []
        self.navigation_generation = 0
        self.request_generations: dict[Any, int] = {}
        self.hooked_pages: set[int] = set()
        self.ready_endpoints: tuple[str, ...] = ()

    def consume_request(self) -> None:
        if time.monotonic() - self.started >= self.config.max_seconds:
            raise CrawlError("time_budget", "单来源运行时间预算耗尽")
        if self.requests >= self.config.max_requests:
            raise CrawlError("request_budget", "请求预算耗尽")
        self.requests += 1

    async def __aenter__(self) -> "BrowserSession":
        runtime = await asyncio.to_thread(Path(".runtime").resolve)
        runtime.mkdir(exist_ok=True)
        os.environ.setdefault("CRAWL4_AI_BASE_DIRECTORY", str(runtime))
        from crawl4ai import AsyncWebCrawler, BrowserConfig
        from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy

        self.output.mkdir(parents=True, exist_ok=True)
        self.crawler = AsyncWebCrawler(
            config=BrowserConfig(
                headless=True, verbose=False, chrome_channel=self.config.chrome_channel
            ),
            base_directory=str(runtime),
        )
        cast(AsyncPlaywrightCrawlerStrategy, self.crawler.crawler_strategy).set_hook(
            "on_page_context_created", self._hook
        )
        await self.crawler.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        for task in self.pending:
            task.cancel()
        await asyncio.gather(*self.pending, return_exceptions=True)
        if self.crawler:
            await self.crawler.__aexit__(*args)

    async def _hook(self, page: Any, context: Any, **kwargs: Any) -> Any:
        self.page = page
        if id(page) in self.hooked_pages:
            return page
        self.hooked_pages.add(id(page))

        def on_request(request: Any) -> None:
            self.request_generations[request] = self.navigation_generation

        def on_response(response: Any) -> None:
            generation = self.request_generations.get(response.request, -1)
            if generation != self.navigation_generation:
                return
            if response.status >= 400:
                self.resource_failures.append({"url": response.url, "status": response.status})
                self.resource_failures = self.resource_failures[-30:]
            if self.capture and response.request.resource_type in {"xhr", "fetch"}:
                task = asyncio.create_task(self._observe(response, generation))
                self.pending.add(task)
                task.add_done_callback(self.pending.discard)

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("requestfinished", lambda request: self.request_generations.pop(request, None))

        def on_failure(request: Any) -> None:
            generation = self.request_generations.pop(request, -1)
            if generation != self.navigation_generation:
                return
            self.resource_failures.append({"url": request.url, "error": request.failure})
            self.resource_failures = self.resource_failures[-30:]

        page.on("requestfailed", on_failure)
        return page

    async def _observe(self, response: Any, generation: int) -> None:
        try:
            async with asyncio.timeout(min(self.config.timeout, 8)):
                body = await response.text()
            if len(body) <= 5_000_000 and generation == self.navigation_generation:
                self.responses.append(
                    {
                        "url": response.url,
                        "body": body,
                        "post_data": response.request.post_data,
                        "portal_id": response.request.headers.get("x-portal-id", ""),
                        "status": response.status,
                    }
                )
                self.responses = self.responses[-150:]
        except (Exception, asyncio.CancelledError):
            # Background observation is best-effort. observed() raises if required traffic is absent.
            return

    async def _execute(self, url: str, js: str | None = None, delay: float = 0) -> Any:
        from crawl4ai import CacheMode, CrawlerRunConfig

        self.consume_request()
        await asyncio.sleep(self.config.delay)
        timeout_seconds = self.config.navigation_timeout if js is None else self.config.timeout
        async with asyncio.timeout(timeout_seconds + 10):
            result = await self.crawler.arun(
                url=url,
                config=CrawlerRunConfig(
                    session_id=self.source_id,
                    cache_mode=CacheMode.BYPASS,
                    js_only=js is not None,
                    js_code=js or "",
                    wait_until="domcontentloaded",
                    page_timeout=int(timeout_seconds * 1000),
                    delay_before_return_html=delay,
                    verbose=False,
                ),
            )
        if not result.success:
            raise CrawlError("browser_error", str(result.error_message)[:1000])
        return result

    async def _recover_ready_page(self, url: str, endpoints: tuple[str, ...], reason: str) -> bool:
        """Recover navigation only; adapter schemas and coverage remain mandatory."""
        if not endpoints or self.page is None:
            return False
        target, current = urlsplit(url), urlsplit(self.page.url)
        if (target.scheme, target.netloc, target.path.rstrip("/"), target.query) != (
            current.scheme,
            current.netloc,
            current.path.rstrip("/"),
            current.query,
        ):
            return False
        if self.pending:
            await asyncio.gather(*list(self.pending), return_exceptions=True)
        matches = []
        for endpoint in endpoints:
            expected = (
                endpoint
                if endpoint.startswith("https://")
                else f"{target.scheme}://{target.netloc}{endpoint}"
            )
            candidates = [
                r
                for r in self.responses
                if r["url"].lower().startswith(expected.lower()) and 200 <= r["status"] < 300
            ]
            valid = []
            for response in candidates:
                try:
                    if isinstance(json.loads(response["body"]), (dict, list)):
                        valid.append(response)
                except ValueError:
                    continue
            if not valid:
                return False
            matches.append(valid[-1])
        try:
            async with asyncio.timeout(5):
                html = await self.page.content()
        except Exception:
            return False
        self.url = url
        path = self.output / f"page-{self.requests:05}-recovered.json"
        write_json(
            path,
            {
                "url": url,
                "current_url": self.page.url,
                "navigation_warning": reason,
                "readiness": matches,
                "html": html,
            },
        )
        self.last_evidence = str(path)
        self.navigation_warnings.append(
            Issue(
                code="navigation_recovered",
                source_id=self.source_id,
                url=url,
                message=f"{reason}；本轮声明的业务接口已返回 JSON，继续适配器字段与覆盖核验。证据：{path}",
            )
        )
        return True

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.ready_endpoints = ready_endpoints
        for attempt in range(self.config.retries + 1):
            self.navigation_generation += 1
            self.responses.clear()
            self.resource_failures.clear()
            try:
                result = await self._execute(url, delay=5)
                path = self.output / f"page-{self.requests:05}.json"
                write_json(path, {"url": url, "status": result.status_code, "html": result.html})
                if result.status_code and result.status_code >= 400:
                    if result.status_code == 412 and await self._recover_ready_page(
                        url, ready_endpoints, "入口 HTTP 412，但浏览器业务页已就绪"
                    ):
                        return
                    raise CrawlError(
                        "access_denied" if result.status_code in {401, 403} else "http_error",
                        f"HTTP {result.status_code}",
                    )
                self.url = url
                self.last_evidence = str(path)
                return
            except Exception as exc:
                write_json(
                    self.output / f"page-{self.requests:05}-error.json",
                    {
                        "url": url,
                        "error": str(exc)[:1000],
                        "resource_failures": self.resource_failures,
                    },
                )
                retryable = (
                    isinstance(exc, TimeoutError)
                    or isinstance(exc, CrawlError)
                    and exc.code == "browser_error"
                )
                navigation_timeout = isinstance(exc, TimeoutError) or (
                    isinstance(exc, CrawlError)
                    and exc.code == "browser_error"
                    and "Timeout" in str(exc)
                    and "navigat" in str(exc)
                )
                structural_shell = (
                    isinstance(exc, CrawlError)
                    and exc.code == "browser_error"
                    and "Structural: minimal_text" in str(exc)
                )
                if structural_shell and ready_endpoints:
                    for _ in range(int(min(self.config.navigation_timeout, 60))):
                        if await self._recover_ready_page(
                            url, ready_endpoints, "空壳启发式提前结束，但声明的业务接口已返回"
                        ):
                            return
                        await asyncio.sleep(1)
                if navigation_timeout and await self._recover_ready_page(
                    url, ready_endpoints, "导航等待超时，但声明的业务接口已返回"
                ):
                    return
                if not retryable or attempt == self.config.retries:
                    raise
                await asyncio.sleep(min(2**attempt, 4))

    async def observed(self, needle: str) -> dict[str, Any]:
        reloads = 0
        for _ in range(int(min(self.config.navigation_timeout, 60) / 2) + self.config.retries):
            if self.pending:
                await asyncio.gather(*list(self.pending), return_exceptions=True)
            matches = [
                r
                for r in self.responses
                if needle.lower() in r["url"].lower() and r["status"] < 400
            ]
            if matches:
                path = self.output / f"observed-{fingerprint(needle)[:12]}.json"
                write_json(path, matches[-1])
                self.last_evidence = str(path)
                return matches[-1]
            transient = any(
                any(
                    marker in str(failure.get("error", ""))
                    for marker in (
                        "ERR_INCOMPLETE_CHUNKED_ENCODING",
                        "ERR_CONNECTION_RESET",
                        "ERR_TIMED_OUT",
                    )
                )
                or failure.get("status", 0) >= 500
                for failure in self.resource_failures
            )
            if transient and reloads < self.config.retries:
                reloads += 1
                write_json(self.output / f"resource-reload-{reloads}.json", self.resource_failures)
                await self.open(self.url, ready_endpoints=self.ready_endpoints)
                continue
            # Network listeners continue running while the SPA renders. Re-extracting an
            # incomplete shell through Crawl4AI can produce another premature failure.
            await asyncio.sleep(2)
        write_json(self.output / "resource-failures.json", self.resource_failures)
        raise CrawlError(
            "api_not_observed", f"未观察到已适配接口 {needle}；需要检查入口、登录或改版"
        )

    async def observed_path(self, path: str) -> dict[str, Any]:
        """Observe one exact API path; avoid matching similarly named filter endpoints."""
        if not path.startswith("/"):
            raise ValueError("接口路径必须以 / 开头")
        for _ in range(int(min(self.config.navigation_timeout, 60) / 2) + 1):
            if self.pending:
                await asyncio.gather(*list(self.pending), return_exceptions=True)
            matches = [
                response
                for response in self.responses
                if urlsplit(response["url"]).path == path and response["status"] < 400
            ]
            if matches:
                evidence = self.output / f"observed-{fingerprint(path)[:12]}.json"
                write_json(evidence, matches[-1])
                self.last_evidence = str(evidence)
                return matches[-1]
            await asyncio.sleep(2)
        raise CrawlError("api_not_observed", f"未观察到精确接口 {path}")

    def snapshot(self, label: str, html: str) -> str:
        """Retain the current DOM after an in-page state change such as a tab click."""
        if not re.fullmatch(r"[a-z0-9-]{1,40}", label):
            raise ValueError("页面证据标签无效")
        path = self.output / f"page-{self.requests:05}-{label}.json"
        write_json(path, {"url": self.url, "html": html})
        self.last_evidence = str(path)
        return str(path)

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        detail: bool = False,
        credentials: str = "include",
    ) -> dict[str, Any]:
        if credentials not in {"include", "omit"}:
            raise ValueError("不支持的凭据模式")
        if payload is not None and form is not None:
            raise ValueError("同一次请求不能同时发送 JSON 和表单")
        if headers and set(headers) != {"X-Portal-Id"}:
            raise ValueError("仅允许公开站点的 X-Portal-Id 请求头")
        identity: dict[str, Any] = {"url": url, "payload": payload, "headers": headers}
        if form is not None:
            identity["form"] = form
        if credentials != "include":
            identity["credentials"] = credentials
        key = fingerprint(identity)
        path = self.output / f"request-{key[:20]}.json"
        if self.resume and detail:
            cached = self.store.cached(self.run_id, self.source_id, key)
            if cached and await asyncio.to_thread(evidence_exists, cached):
                self.last_evidence = cached
                return json.loads(await asyncio.to_thread(read_evidence, cached))["data"]
        self.store.request(self.run_id, self.source_id, key, "pending")
        options: dict[str, Any] = {
            "method": "POST" if payload is not None or form is not None else "GET",
            "credentials": credentials,
            "headers": dict(headers or {}),
        }
        if payload is not None:
            options["headers"]["Content-Type"] = "application/json"
            options["body"] = json.dumps(payload, ensure_ascii=False)
        elif form is not None:
            options["headers"]["Content-Type"] = "application/x-www-form-urlencoded"
            options["body"] = urlencode(form)
        script = (
            "const options="
            + json.dumps(options)
            + ";options.signal=AbortSignal.timeout("
            + str(int(self.config.timeout * 1000))
            + ");const r=await fetch("
            + json.dumps(url)
            + ",options);return {status:r.status,url:r.url,body:await r.text()};"
        )
        for attempt in range(self.config.retries + 1):
            try:
                self.capture = False
                self.consume_request()
                await asyncio.sleep(self.config.delay)
                async with asyncio.timeout(self.config.timeout + 5):
                    response = await self.page.evaluate("async () => {" + script + "}")
                if not isinstance(response, dict) or "body" not in response:
                    raise CrawlError("api_execution", "浏览器没有返回接口响应")
                if response["status"] >= 400:
                    write_json(
                        path,
                        {
                            "url": url,
                            "status": response["status"],
                            "body": response["body"][:50000],
                        },
                    )
                    raise CrawlError(
                        "access_denied" if response["status"] in {401, 403} else "http_error",
                        f"HTTP {response['status']}",
                    )
                try:
                    data = json.loads(response["body"], strict=False)
                except json.JSONDecodeError as exc:
                    write_json(
                        path,
                        {
                            "url": url,
                            "payload": payload,
                            "form": form,
                            "status": response["status"],
                            "body": response["body"][:50000],
                        },
                    )
                    self.last_evidence = str(path)
                    raise CrawlError(
                        "invalid_json",
                        f"接口响应不是 JSON（HTTP {response['status']}）：{response['body'][:300]!r}",
                    ) from exc
                if not isinstance(data, dict):
                    raise CrawlError("schema_changed", "预期 JSON 对象，接口结构已改变")
                write_json(
                    path,
                    {
                        "url": url,
                        "payload": payload,
                        "form": form,
                        "status": response["status"],
                        "data": data,
                    },
                )
                self.store.request(self.run_id, self.source_id, key, "done", str(path))
                self.last_evidence = str(path)
                return data
            except Exception as exc:
                self.store.request(
                    self.run_id, self.source_id, key, "failed", str(path), error=str(exc)[:1000]
                )
                if isinstance(exc, CrawlError) and exc.code in {
                    "access_denied",
                    "request_budget",
                    "time_budget",
                }:
                    raise
                if attempt == self.config.retries:
                    raise
                await asyncio.sleep(min(2**attempt, 4))
            finally:
                self.capture = True
        raise AssertionError("unreachable")

    async def request_html(
        self,
        url: str,
        *,
        form: dict[str, str] | None = None,
        detail: bool = False,
        encoding: str = "utf-8",
    ) -> str:
        """Read a server-rendered page in the active Crawl4AI browser context."""
        identity = {"url": url, "form": form, "format": "html"}
        if encoding not in {"utf-8", "gb18030"}:
            raise ValueError("未支持的HTML编码")
        if encoding != "utf-8":
            identity["encoding"] = encoding
        key = fingerprint(identity)
        path = self.output / f"request-{key[:20]}.json"
        if self.resume and detail:
            cached = self.store.cached(self.run_id, self.source_id, key)
            if cached and await asyncio.to_thread(evidence_exists, cached):
                self.last_evidence = cached
                return json.loads(await asyncio.to_thread(read_evidence, cached))["html"]
        self.store.request(self.run_id, self.source_id, key, "pending")
        options: dict[str, Any] = {
            "method": "POST" if form is not None else "GET",
            "credentials": "include",
        }
        if form is not None:
            options["headers"] = {"Content-Type": "application/x-www-form-urlencoded"}
            options["body"] = urlencode(form)
        script = (
            "const options="
            + json.dumps(options)
            + ";options.signal=AbortSignal.timeout("
            + str(int(self.config.timeout * 1000))
            + ");const r=await fetch("
            + json.dumps(url)
            + ",options);const body=await r.arrayBuffer();return {status:r.status,url:r.url,body:new TextDecoder("
            + json.dumps(encoding)
            + ").decode(body)};"
        )
        for attempt in range(self.config.retries + 1):
            try:
                self.capture = False
                self.consume_request()
                await asyncio.sleep(self.config.delay)
                async with asyncio.timeout(self.config.timeout + 5):
                    response = await self.page.evaluate("async () => {" + script + "}")
                if not isinstance(response, dict) or not isinstance(response.get("body"), str):
                    raise CrawlError("api_execution", "浏览器没有返回 HTML 页面")
                if response["status"] >= 400:
                    write_json(
                        path,
                        {
                            "url": response["url"],
                            "form": form,
                            "status": response["status"],
                            "body": response["body"][:50000],
                        },
                    )
                    self.last_evidence = str(path)
                    raise CrawlError(
                        "access_denied" if response["status"] in {401, 403} else "http_error",
                        f"HTTP {response['status']}",
                    )
                html = response["body"]
                if "<html" not in html[:50000].lower():
                    write_json(
                        path,
                        {
                            "url": response["url"],
                            "form": form,
                            "status": response["status"],
                            "body": html[:50000],
                        },
                    )
                    self.last_evidence = str(path)
                    raise CrawlError("invalid_html", "响应不是完整 HTML 页面")
                write_json(
                    path,
                    {
                        "url": response["url"],
                        "form": form,
                        "status": response["status"],
                        "html": html,
                    },
                )
                self.store.request(self.run_id, self.source_id, key, "done", str(path))
                self.last_evidence = str(path)
                return html
            except Exception as exc:
                self.store.request(
                    self.run_id, self.source_id, key, "failed", str(path), error=str(exc)[:1000]
                )
                if isinstance(exc, CrawlError) and exc.code in {
                    "access_denied",
                    "request_budget",
                    "time_budget",
                }:
                    raise
                if attempt == self.config.retries:
                    raise
                await asyncio.sleep(min(2**attempt, 4))
            finally:
                self.capture = True
        raise AssertionError("unreachable")
