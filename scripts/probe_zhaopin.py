"""Compare observed Zhaopin campaign filters with the public unfiltered catalog."""

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit

from job_crawler.config import CrawlConfig
from job_crawler.sources import read_sources
from job_crawler.storage import Store, write_json
from job_crawler.transport import BrowserSession


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources, _ = read_sources(Path("sites/sources.csv"))
    limit = asyncio.Semaphore(2)

    async def probe(source_id: str) -> None:
        source = next(source for source in sources if source.source_id == source_id)
        async with limit:
            output = args.output / source_id
            output.mkdir(parents=True, exist_ok=True)
            store = Store(output / "state.sqlite")
            try:
                async with BrowserSession(
                    source_id,
                    "zhaopin-probe",
                    output,
                    store,
                    CrawlConfig(navigation_timeout=50, timeout=30, retries=0),
                ) as session:
                    await session.open(source.url)
                    observed = await session.observed_path("/grace/api/dsc/search-job-list")
                    payload = json.loads(observed["post_data"])
                    payload["pageIndex"] = 1
                    payload["pageSize"] = 50
                    payload["orgDepartmentIds"] = []
                    payload["campusParentDepartmentIds"] = ""
                    response = await session.request(observed["url"], payload=payload)
                    info = response["data"]["pageInfo"]
                    rows = response["data"]["jobList"]
                    write_json(
                        output / "comparison.json",
                        {
                            "source_url": source.url,
                            "api_host": urlsplit(observed["url"]).hostname,
                            "observed_payload": json.loads(observed["post_data"]),
                            "unfiltered_payload": payload,
                            "page_info": info,
                            "returned": len(rows),
                            "sample_job_numbers": [r["job"]["jobNumber"] for r in rows[:5]],
                            "sample_org_names": [
                                r["company"].get("campusOrgName") for r in rows[:5]
                            ],
                        },
                    )
                    print(source_id, info, "returned", len(rows), flush=True)
            except Exception as exc:
                write_json(output / "error.json", {"error": str(exc)[:1000]})
                print(source_id, "error", str(exc)[:150], flush=True)
            finally:
                store.close()

    await asyncio.gather(*(probe(source_id) for source_id in args.ids))


if __name__ == "__main__":
    asyncio.run(main())
