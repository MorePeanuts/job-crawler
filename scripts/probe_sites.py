"""Bounded Crawl4AI discovery; writes evidence, never changes source bindings."""

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from job_crawler.config import CrawlConfig
from job_crawler.models import Source
from job_crawler.sources import read_sources
from job_crawler.storage import Store, redact, write_json
from job_crawler.transport import BrowserSession


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--follow", default="")
    parser.add_argument("--settle", type=float, default=0)
    parser.add_argument("--click", default="")
    parser.add_argument("--url")
    parser.add_argument("--sources", type=Path, default=Path("sites/sources.csv"))
    parser.add_argument("--route", help="使用每个来源的原域名和指定路径进行同平台目录探测")
    parser.add_argument("--fragment", help="替换每个来源 URL 的 fragment；用于多租户 SPA 路由")
    args = parser.parse_args()
    sources, _ = read_sources(args.sources)
    limit = asyncio.Semaphore(2)

    async def probe(source: Source) -> None:
        async with limit:
            output = args.output / source.source_id
            output.mkdir(parents=True, exist_ok=True)
            store = Store(output / "state.sqlite")
            try:
                async with BrowserSession(
                    source.source_id,
                    "probe",
                    output,
                    store,
                    CrawlConfig(navigation_timeout=50, timeout=30, retries=0),
                ) as session:
                    error = ""
                    try:
                        target = args.url or source.url
                        if args.route:
                            parts = urlsplit(source.url)
                            target = urlunsplit(
                                parts._replace(path=args.route, query="", fragment="")
                            )
                        if args.fragment is not None:
                            target = urlunsplit(urlsplit(target)._replace(fragment=args.fragment))
                        await session.open(target)
                    except Exception as exc:
                        error = str(exc)[:1000]
                    if args.settle:
                        await asyncio.sleep(args.settle)
                    if args.follow and session.page:
                        link = await session.page.evaluate(
                            "text => [...document.querySelectorAll('a[href]')].find(a=>a.innerText.trim()===text)?.href",
                            args.follow,
                        )
                        if link:
                            try:
                                await session.open(link)
                            except Exception as exc:
                                error = str(exc)[:1000]
                            await asyncio.sleep(10)
                    if args.click and session.page:
                        for label in args.click.split("|"):
                            try:
                                await session.page.get_by_text(label, exact=True).first.click(
                                    timeout=10000
                                )
                            except Exception as exc:
                                error = str(exc)[:1000]
                                break
                            await asyncio.sleep(3)
                            newest = session.page.context.pages[-1]
                            if newest != session.page:
                                await session._hook(newest, newest.context)
                            await asyncio.sleep(12)
                    if session.pending:
                        await asyncio.gather(*list(session.pending), return_exceptions=True)
                    document = (
                        await session.page.evaluate("""() => ({
                      url: location.href, text: document.body.innerText,
                      links: [...document.querySelectorAll('a[href]')].map(a=>({text:a.innerText,url:a.href})),
                      scripts: [...document.scripts].map(s=>s.src).filter(Boolean)
                    })""")
                        if session.page
                        else {}
                    )
                    write_json(output / "document.json", document)
                    if session.page:
                        write_json(output / "dom.json", {"html": await session.page.content()})
                    write_json(output / "traffic.json", session.responses)
                    print(
                        json.dumps(
                            redact(
                                {
                                    "id": source.source_id,
                                    "error": error[:150],
                                    "url": document.get("url"),
                                    "text": document.get("text", "")[:300],
                                    "apis": [r["url"] for r in session.responses],
                                }
                            ),
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
            finally:
                store.close()

    await asyncio.gather(*(probe(s) for s in sources if s.source_id in args.ids))


if __name__ == "__main__":
    asyncio.run(main())
