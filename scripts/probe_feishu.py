"""Bounded Feishu job-list pagination protocol probe."""

import asyncio
import json
from pathlib import Path

from job_crawler.adapters.base import query
from job_crawler.config import CrawlConfig
from job_crawler.sources import read_sources
from job_crawler.storage import Store, write_json
from job_crawler.transport import BrowserSession


async def main() -> None:
    source = next(
        source
        for source in read_sources(Path("sites/sources.csv"))[0]
        if source.source_id == "COM0429"
    )
    output = Path("outputs/batch3-feishu-pagination/COM0429")
    store = Store(output / "state.sqlite")
    try:
        async with BrowserSession(
            source.source_id,
            "feishu-probe",
            output,
            store,
            CrawlConfig(navigation_timeout=50, timeout=30, retries=0),
        ) as session:
            await session.open(source.url)
            observed = await session.observed("/api/v1/search/job/posts?")
            data = json.loads(observed["body"])
            write_json(
                output / "first.json",
                {
                    "url": observed["url"],
                    "count": len(data["data"]["job_post_list"]),
                    "keys": list(data["data"]),
                    "pagination": data["data"].get("count"),
                },
            )
            try:
                next_data = await session.request(query(observed["url"], offset=10))
                write_json(output / "next.json", next_data)
                print("next", next_data.get("code"), list(next_data.get("data", {})), flush=True)
            except Exception as exc:
                print("next_error", str(exc)[:200], flush=True)
            if session.page:
                await session.page.locator('li[title="下一页"]').click(timeout=10000)
                await asyncio.sleep(3)
                if session.pending:
                    await asyncio.gather(*list(session.pending), return_exceptions=True)
                pages = [
                    item
                    for item in session.responses
                    if "/api/v1/search/job/posts?" in item["url"] and "offset=10" in item["url"]
                ]
                if pages:
                    second = json.loads(pages[-1]["body"])
                    write_json(
                        output / "ui-next.json",
                        {
                            "url": pages[-1]["url"],
                            "code": second.get("code"),
                            "count": second.get("data", {}).get("count"),
                            "rows": len(second.get("data", {}).get("job_post_list", [])),
                        },
                    )
                    print(
                        "ui_next",
                        second.get("code"),
                        len(second["data"]["job_post_list"]),
                        flush=True,
                    )
            print("first_count", len(data["data"]["job_post_list"]), flush=True)
    finally:
        store.close()


if __name__ == "__main__":
    asyncio.run(main())
