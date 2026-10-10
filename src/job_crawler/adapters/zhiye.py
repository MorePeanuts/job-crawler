"""Explicit Beisen tenants sharing a verified public campus API contract."""

import asyncio
import json
from typing import Any
from urllib.parse import urlencode

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Job, Scope
from job_crawler.transport import CrawlError


def date_text(value: Any) -> str:
    value = text(value)
    return "" if value.startswith("0001-01-01") else value


class Zhiye(Adapter):
    path = "/campus/jobs"
    ready_endpoints = ("/api/Jobad/GetJobAdPageList",)
    scope_description = "北森公开校园招聘 Category=2 全目录；保留实际租户/门户范围，不含社招和实习"

    async def harvest(self) -> None:
        observed = await self.session.observed("/api/Jobad/GetJobAdPageList")
        payload = json.loads(observed["post_data"])
        check([str(v) for v in payload.get("Category", [])] == ["2"], "不是校招 Category=2")
        check(not payload.get("KeyWords"), "校招目录仍有关键词筛选")
        for key in (
            "LocId",
            "ClassificationOne",
            "ClassificationTwo",
            "Classification3",
            "Classification4",
            "Classification5",
            "Classification6",
        ):
            check(not payload.get(key), f"目录仍有局部筛选 {key}，需接入完整入口")
        scope = Scope(name="campus-category-2")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 0
        size = max(20, int(payload["PageSize"]))
        detail_url = ""
        limit = asyncio.Semaphore(3)
        abort: CrawlError | None = None

        async def read_job(listed: dict[str, Any]) -> Job | None:
            nonlocal abort
            async with limit:
                if abort is not None:
                    return None
                try:
                    data = await self.session.request(
                        query(detail_url, jobAdId=listed["Id"]), detail=True
                    )
                    check(data.get("Code") == 200, "北森详情业务失败")
                    row = data["Data"]
                    check(str(row["Id"]) == str(listed["Id"]), "北森详情与列表 ID 不一致")
                    check(str(row["CategoryId"]) == "2", "岗位混入非校招类别")
                    check(bool(row["JobAdName"]), "岗位名称为空")
                    check("Duty" in row and "Require" in row, "详情不再包含职位描述")
                    job = self.job(
                        str(row["Id"]),
                        title=text(row["JobAdName"]),
                        source_url=f"https://{self.host}/campus/detail?{urlencode({'jobAdId': row['Id']})}",
                        unit=text(row.get("Org") or listed.get("Org")),
                        location=text(row.get("LocNames") or listed.get("LocNames")),
                        education=text(row.get("Degree") or listed.get("Degree")),
                        address=text(row.get("DetailAddress")),
                        category_raw=text(
                            row.get("ClassificationOne") or listed.get("ClassificationOne")
                        ),
                        duties=text(row["Duty"]),
                        requirements=text(row["Require"]),
                        published=date_text(row.get("PostDate"))
                        or date_text(listed.get("PostDate")),
                        deadline=date_text(row.get("EndTime")) or date_text(listed.get("EndTime")),
                        field_sources={
                            "duties": "GetJobAdInfo.Data.Duty",
                            "requirements": "GetJobAdInfo.Data.Require",
                            "published": "PostDate；0001 哨兵为空",
                            "deadline": "EndTime；0001 哨兵为空",
                        },
                    )
                    scope.details += 1
                    return job
                except Exception as exc:
                    self.error(exc, str(listed.get("Id", "")))
                    if isinstance(exc, CrawlError) and exc.code in {
                        "access_denied",
                        "request_budget",
                        "time_budget",
                    }:
                        abort = exc
                    return None

        while True:
            result = await self.session.request(
                observed["url"], payload={**payload, "PageIndex": page, "PageSize": size}
            )
            check(result.get("Code") == 200, "北森列表业务失败")
            expected = int(result["Count"])
            check(expected >= 0, "北森目录总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "北森目录总数变化")
            rows = self.add_page(scope, result["Data"], seen, lambda row: str(row["Id"]))
            if rows and not detail_url:
                await self.session.open(
                    f"https://{self.host}/campus/detail?{urlencode({'jobAdId': rows[0]['Id']})}",
                    ready_endpoints=("/api/JobAd/GetJobAdInfo?",),
                )
                detail_url = (await self.session.observed("/api/JobAd/GetJobAdInfo?"))["url"]
            jobs = await asyncio.gather(*(read_job(row) for row in rows))
            self.result.jobs.extend(job for job in jobs if job is not None)
            if abort is not None:
                raise abort
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(bool(rows), "北森分页提前为空")
            page += 1


class Poly(Zhiye):
    name = "zhiye-poly"
    host = "polycareer.zhiye.com"


class Xiangyu(Zhiye):
    name = "zhiye-xiangyu"
    host = "xiangyu.zhiye.com"


class Changan(Zhiye):
    name = "zhiye-changan"
    host = "changanqiche.zhiye.com"
    path = "/campus/"


class DigitalChina(Zhiye):
    name = "zhiye-digitalchina"
    host = "digitalchina.zhiye.com"


class Bosc(Zhiye):
    name = "zhiye-bosc"
    host = "bosc.zhiye.com"


class Sinotrans(Zhiye):
    name = "zhiye-sinotrans"
    host = "sinotrans.zhiye.com"
    path = "/campus"


class Sany(Zhiye):
    name = "zhiye-sany"
    host = "sany.zhiye.com"


class Transsion(Zhiye):
    name = "zhiye-transsion"
    host = "transsion.zhiye.com"


class Bocd(Zhiye):
    name = "zhiye-bocd"
    host = "bocd.zhiye.com"


class Cscb(Zhiye):
    name = "zhiye-cscb"
    host = "cscb.zhiye.com"


class Dsbj(Zhiye):
    name = "zhiye-dsbj"
    host = "dsbj.zhiye.com"


class Sailun(Zhiye):
    name = "zhiye-sailun"
    host = "sailuntire.zhiye.com"


class Csc108(Zhiye):
    name = "zhiye-csc108"
    host = "csc108.zhiye.com"


class Tsingtao(Zhiye):
    name = "zhiye-tsingtao"
    host = "tsingtao.zhiye.com"


class Yuhong(Zhiye):
    name = "zhiye-yuhong"
    host = "yuhongzp.zhiye.com"


class Iflytek(Zhiye):
    name = "zhiye-iflytek"
    host = "iflytek.zhiye.com"


TENANTS = (
    Poly,
    Xiangyu,
    Changan,
    DigitalChina,
    Bosc,
    Sinotrans,
    Sany,
    Transsion,
    Bocd,
    Cscb,
    Dsbj,
    Sailun,
    Csc108,
    Tsingtao,
    Yuhong,
    Iflytek,
)
