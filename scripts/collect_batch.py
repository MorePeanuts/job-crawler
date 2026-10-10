"""Run independently saved company validations with two browser sessions at most."""

import argparse
import asyncio
from pathlib import Path
from urllib.parse import urlsplit

from job_crawler.adapters.zhiye import TENANTS
from job_crawler.config import Settings
from job_crawler.models import Binding, Source
from job_crawler.runner import run
from job_crawler.sources import read_sources


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources, _ = read_sources(Path("sites/sources.csv"))
    limit = asyncio.Semaphore(2)

    async def collect(source: Source) -> None:
        adapter = next(a for a in TENANTS if a.host == urlsplit(source.url).hostname)
        async with limit:
            output = args.output / source.source_id
            settings = Settings()
            settings.crawl.delay = 0.5
            settings.crawl.max_seconds = 1800
            settings.crawl.retries = 1
            result = await run(
                [source],
                {source.source_id: Binding(adapter=adapter.name)},
                settings,
                output=output,
                state=output / "state.sqlite",
            )
            print(
                source.source_id, result["sources"][0]["coverage"], result["collected"], flush=True
            )

    await asyncio.gather(*(collect(s) for s in sources if s.source_id in args.ids))


if __name__ == "__main__":
    asyncio.run(main())
