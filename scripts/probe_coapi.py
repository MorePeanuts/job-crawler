"""Inspect public 51job COAPI list/detail callbacks without applying to jobs."""

import argparse
import asyncio
from pathlib import Path

from job_crawler.config import CrawlConfig
from job_crawler.sources import read_sources
from job_crawler.storage import Store, write_json
from job_crawler.transport import BrowserSession


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_id")
    parser.add_argument("url")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = next(
        source
        for source in read_sources(Path("sites/sources.csv"))[0]
        if source.source_id == args.source_id
    )
    output = args.output / source.source_id
    store = Store(output / "state.sqlite")
    try:
        async with BrowserSession(
            source.source_id,
            "coapi-probe",
            output,
            store,
            CrawlConfig(navigation_timeout=50, timeout=30, retries=0),
        ) as session:
            await session.open(args.url)
            if session.page is None:
                raise RuntimeError("No browser page")
            if args.source_id == "COM0489":
                listing = await session.page.evaluate(
                    """() => new Promise((resolve, reject) => {
                      const timer = setTimeout(() => reject(new Error('list timeout')), 20000);
                      coapi.getJobList({ctmid:'8074390',pagesize:2000,functype:'',jobarea:'',degreefrom:'',keyword:''},
                        value => {clearTimeout(timer);resolve(value)});
                    })"""
                )
                rows = listing["resultbody"]["joblist"]
                write_json(
                    output / "list-metadata.json",
                    {"keys": list(listing["resultbody"]), "count": len(rows), "first": rows[0]},
                )
                job_id = str(rows[0]["jobid"])
            else:
                job_id = "173645538"
            detail = await session.page.evaluate(
                """id => new Promise((resolve, reject) => {
                  const timer = setTimeout(() => reject(new Error('detail timeout')), 20000);
                  coapi.getJobDetail(id, value => {clearTimeout(timer);resolve(value)});
                })""",
                job_id,
            )
            write_json(output / "detail-metadata.json", detail)
            print(args.source_id, job_id, list(detail.get("resultbody", {})), flush=True)
    finally:
        store.close()


if __name__ == "__main__":
    asyncio.run(main())
