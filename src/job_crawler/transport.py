"""Crawl4AI browser and API execution with bounded evidence capture."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Protocol, cast

from job_crawler.config import CrawlConfig
from job_crawler.storage import Store, fingerprint, write_json


class CrawlError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Session(Protocol):
    last_evidence: str

    async def open(self, url: str) -> None: ...
    async def observed(self, needle: str) -> dict[str, Any]: ...
    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
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

        def on_response(response: Any) -> None:
            if self.capture and response.request.resource_type in {"xhr", "fetch"}:
                task = asyncio.create_task(self._observe(response))
                self.pending.add(task)
                task.add_done_callback(self.pending.discard)

        page.on("response", on_response)
        return page

    async def _observe(self, response: Any) -> None:
        try:
            async with asyncio.timeout(min(self.config.timeout, 8)):
                body = await response.text()
            if len(body) <= 5_000_000:
                self.responses.append(
                    {
                        "url": response.url,
                        "body": body,
                        "post_data": response.request.post_data,
                        "status": response.status,
                    }
                )
                self.responses = self.responses[-150:]
        except (Exception, asyncio.CancelledError):
            # Background observation is best-effort. observed() raises if required traffic is absent.
            return

    async def _execute(self, url: str, js: str | None = None, delay: float = 0) -> Any:
        from crawl4ai import CacheMode, CrawlerRunConfig

        if self.requests >= self.config.max_requests:
            raise CrawlError("request_budget", "请求预算耗尽")
        self.requests += 1
        await asyncio.sleep(self.config.delay)
        async with asyncio.timeout(self.config.timeout + 10):
            result = await self.crawler.arun(
                url=url,
                config=CrawlerRunConfig(
                    session_id=self.source_id,
                    cache_mode=CacheMode.BYPASS,
                    js_only=js is not None,
                    js_code=js or "",
                    wait_until="domcontentloaded",
                    page_timeout=int(self.config.timeout * 1000),
                    delay_before_return_html=delay,
                    verbose=False,
                ),
            )
        if not result.success:
            raise CrawlError("browser_error", str(result.error_message)[:1000])
        if js is None and result.status_code and result.status_code >= 400:
            raise CrawlError(
                "access_denied" if result.status_code in {401, 403} else "http_error",
                f"HTTP {result.status_code}",
            )
        return result

    async def open(self, url: str) -> None:
        self.responses.clear()
        result = await self._execute(url, delay=5)
        self.url = url
        path = self.output / f"page-{self.requests:05}.json"
        write_json(path, {"url": url, "status": result.status_code, "html": result.html})
        self.last_evidence = str(path)

    async def observed(self, needle: str) -> dict[str, Any]:
        for _ in range(4):
            if self.pending:
                await asyncio.gather(*list(self.pending), return_exceptions=True)
            matches = [r for r in self.responses if needle in r["url"] and r["status"] < 400]
            if matches:
                path = self.output / f"observed-{fingerprint(needle)[:12]}.json"
                write_json(path, matches[-1])
                self.last_evidence = str(path)
                return matches[-1]
            await self._execute(self.url, "void 0;", delay=2)
        raise CrawlError(
            "api_not_observed", f"未观察到已适配接口 {needle}；需要检查入口、登录或改版"
        )

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        key = fingerprint({"url": url, "payload": payload})
        path = self.output / f"request-{key[:20]}.json"
        if self.resume and detail:
            cached = self.store.cached(self.run_id, self.source_id, key)
            if cached and await asyncio.to_thread(Path(cached).exists):
                self.last_evidence = cached
                return json.loads(await asyncio.to_thread(Path(cached).read_text))["data"]
        self.store.request(self.run_id, self.source_id, key, "pending")
        options: dict[str, Any] = {
            "method": "POST" if payload is not None else "GET",
            "credentials": "include",
            "headers": {},
        }
        if payload is not None:
            options["headers"]["Content-Type"] = "application/json"
            options["body"] = json.dumps(payload, ensure_ascii=False)
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
                if self.requests >= self.config.max_requests:
                    raise CrawlError("request_budget", "请求预算耗尽")
                self.requests += 1
                await asyncio.sleep(self.config.delay)
                async with asyncio.timeout(self.config.timeout + 5):
                    response = await self.page.evaluate("async () => {" + script + "}")
                if not isinstance(response, dict) or "body" not in response:
                    raise CrawlError("api_execution", "浏览器没有返回接口响应")
                if response["status"] >= 400:
                    raise CrawlError(
                        "access_denied" if response["status"] in {401, 403} else "http_error",
                        f"HTTP {response['status']}",
                    )
                data = json.loads(response["body"], strict=False)
                if not isinstance(data, dict):
                    raise CrawlError("schema_changed", "预期 JSON 对象，接口结构已改变")
                write_json(
                    path,
                    {"url": url, "payload": payload, "status": response["status"], "data": data},
                )
                self.store.request(self.run_id, self.source_id, key, "done", str(path))
                self.last_evidence = str(path)
                return data
            except Exception as exc:
                self.store.request(
                    self.run_id, self.source_id, key, "failed", error=str(exc)[:1000]
                )
                if isinstance(exc, CrawlError) and exc.code in {"access_denied", "request_budget"}:
                    raise
                if attempt == self.config.retries:
                    raise
                await asyncio.sleep(min(2**attempt, 4))
            finally:
                self.capture = True
        raise AssertionError("unreachable")
