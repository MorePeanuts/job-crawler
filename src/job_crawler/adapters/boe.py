"""BOE's custom Beisen campus catalog, including every public project type."""

import json
from typing import cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.adapters.zhiye import date_text
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

API = "https://boe.yuegekeji8.cn/api/Jobad/GetJobAdPageList"
DETAIL = "https://boe.yuegekeji8.cn/api/Jobad/GetJobAdInfo"
FORMAL_TYPES = {"应届生", "博士生招聘", "提前批"}


class BoeCampus(Adapter):
    name = "boe-2027-campus"
    host = "campus.boe.com"
    path = "/custom/xzzw?hideMenu=1"
    ready_endpoints = ("boe.yuegekeji8.cn/api/Jobad/GetJobAdPageList",)
    scope_description = "京东方2027全球校招自定义目录 Category=15 全招聘类型；实习生按源类型排除"

    async def harvest(self) -> None:
        observed = await self.session.observed("boe.yuegekeji8.cn/api/Jobad/GetJobAdPageList")
        payload = json.loads(observed["post_data"])
        check(
            payload.get("Category") == [15]
            and payload.get("PageIndex") == 0
            and payload.get("type_code") == "1"
            and not payload.get("KeyWords"),
            "京东方入口不是已验证校招目录",
        )
        for key in (
            "ClassificationOne",
            "LocId",
            "PostDate",
            "ywbk",
            "activityGuid",
            "activityJobIds",
        ):
            check(not payload.get(key), f"京东方目录含局部筛选 {key}")
        check(
            set(payload)
            <= {
                "PageIndex",
                "PageSize",
                "Category",
                "ClassificationOne",
                "LocId",
                "PostDate",
                "KeyWords",
                "type_code",
                "ywbk",
                "activityGuid",
                "activityJobIds",
                "DisplayFields",
            },
            "京东方出现未知筛选条件",
        )
        payload["type_code"] = ""
        payload["PageSize"] = 50
        session = cast(BrowserSession, self.session)
        scope = Scope(name="campus-category-15-all-types")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 0
        while True:
            response = await session.request(
                observed["url"], payload={**payload, "PageIndex": page}, credentials="omit"
            )
            check(response.get("code") == 1, "京东方目录业务失败")
            data = response["data"]
            expected = int(data["counts"])
            check(expected >= 0, "京东方目录总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "京东方翻页期间总数变化")
            rows = self.add_page(scope, data["list"], seen, lambda row: str(row["Id"]))
            check(len(rows) <= 50, "京东方分页大小异常")
            list_evidence = session.last_evidence
            for row in rows:
                kind = text(row.get("type"))
                check(kind in FORMAL_TYPES | {"实习生"}, "京东方出现未知招聘类型")
                if kind == "实习生":
                    scope.skipped_out_of_scope += 1
                    continue
                key = str(row["Id"])
                check(bool(text(row.get("JobAdName"))), "京东方列表岗位名称为空")
                listing = self.job(
                    key,
                    title=text(row["JobAdName"]),
                    work_type="校招",
                    unit=text(row.get("yebk")),
                    location=text(row.get("LocNames")),
                    source_url=f"https://{self.host}/custom/xzxq?hideMenu=1&jobAdId={key}",
                )
                listing.evidence = [list_evidence]
                resolved = self.before_detail(
                    f"ad:{key}", row, scope, listing, evidence=list_evidence
                )
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                detail = await session.request(
                    f"{DETAIL}?jobAdId={key}", detail=True, credentials="omit"
                )
                check(detail.get("code") == 1, "京东方详情业务失败")
                body = detail["data"]["res"]
                check(str(body.get("Id")) == key, "京东方详情与列表 ID 不一致")
                check(
                    text(body.get("JobAdName")) == listing.title and text(body.get("type")) == kind,
                    "京东方详情岗位或招聘类型与列表不一致",
                )
                check(int(body.get("CategoryId", 0)) == 15, "京东方详情不是校招类别")
                check(text(body.get("yebk")) == listing.unit, "京东方业务板块与列表不符")
                check(
                    "Duty" in body and ("RequireNew" in body or "Require" in body),
                    "京东方详情正文缺失",
                )
                if body.get("Status") != 1 or body.get("StdIsDeleted"):
                    scope.skipped_closed += 1
                    continue
                job = self.job(
                    key,
                    title=listing.title,
                    source_url=listing.source_url,
                    work_type="校招",
                    unit=listing.unit,
                    category_raw=text(body.get("ClassificationOne")),
                    location=text(body.get("LocNames") or row.get("LocNames")),
                    education=text(body.get("Degree")),
                    duties=text(body["Duty"]),
                    requirements=text(body.get("RequireNew") or body.get("Require")),
                    published=date_text(body.get("PostDate")),
                    deadline=date_text(body.get("EndTime")),
                    field_sources={
                        "unit": "GetJobAdInfo.data.res.yebk（业务板块，非招聘法人）",
                        "duties": "GetJobAdInfo.data.res.Duty",
                        "requirements": "GetJobAdInfo.data.res.RequireNew",
                        "published": "GetJobAdInfo.data.res.PostDate",
                        "deadline": "GetJobAdInfo.data.res.EndTime；2222 哨兵为空",
                    },
                )
                job.evidence = [list_evidence, session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"ad:{key}", row, [job])
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(bool(rows), "京东方分页提前为空")
            page += 1
