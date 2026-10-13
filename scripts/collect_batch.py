"""Run independently saved company validations with two browser sessions at most."""

import argparse
import asyncio
from pathlib import Path
from urllib.parse import urlsplit

from job_crawler.adapters import REGISTRY
from job_crawler.adapters.bankcomm import BankComm
from job_crawler.adapters.bilibili import Bilibili
from job_crawler.adapters.byd import BYDCampus
from job_crawler.adapters.campaign51 import TENANTS as CAMPAIGN51_TENANTS
from job_crawler.adapters.coapi51 import TENANTS as COAPI51_TENANTS
from job_crawler.adapters.feishu import Desaysv
from job_crawler.adapters.jd import JD
from job_crawler.adapters.lenovo import Lenovo
from job_crawler.adapters.meituan import Meituan
from job_crawler.adapters.moka import TENANTS as MOKA_TENANTS
from job_crawler.adapters.sf import SF
from job_crawler.adapters.tcl import TCLCampus
from job_crawler.adapters.tencent import Tencent
from job_crawler.adapters.zhaopin import TENANTS as ZHAOPIN_TENANTS
from job_crawler.adapters.zhiye import TENANTS as ZHIYE_TENANTS
from job_crawler.config import load_settings
from job_crawler.models import Binding, Source
from job_crawler.runner import run
from job_crawler.sources import read_sources


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--adapter", action="append", default=[], metavar="SOURCE=NAME")
    args = parser.parse_args()
    forced = dict(item.split("=", 1) for item in args.adapter)
    sources, _ = read_sources(Path("sites/sources.csv"))
    limit = asyncio.Semaphore(2)

    async def collect(source: Source) -> None:
        matches = [
            a
            for a in (
                *ZHIYE_TENANTS,
                *ZHAOPIN_TENANTS,
                *MOKA_TENANTS,
                *CAMPAIGN51_TENANTS,
                *COAPI51_TENANTS,
                Lenovo,
                Desaysv,
                JD,
                Tencent,
                SF,
                BankComm,
                Meituan,
                Bilibili,
                BYDCampus,
                TCLCampus,
            )
            if a.host == urlsplit(source.url).hostname
        ]
        if source.source_id in forced:
            adapter = REGISTRY[forced[source.source_id]]
        elif len(matches) == 1:
            adapter = matches[0]
        else:
            raise ValueError(
                f"{source.source_id} 所在域名有多个适配器，请指定 --adapter SOURCE=NAME"
            )
        async with limit:
            output = args.output / source.source_id
            settings = load_settings(args.config)
            settings.crawl.delay = 0.5
            settings.crawl.max_seconds = 3600
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
