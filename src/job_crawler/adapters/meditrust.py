"""Meditrust's public 2027 mobile Beisen campus catalog."""

import json
from datetime import date
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import CrawlError

ROOT = "https://meditrusthealth.m.zhiye.com"
LIST = ROOT + "/JobAd/_SearchJobAd"
INFO = ROOT + "/JobAd/_Info"
PARAMS = {"jc": "2", "c1": "-1", "c2": "-1", "ky": "", "c": "-1"}


def detail_page(job_id: str) -> str:
    return query(ROOT + "/yjshow.html", adId=job_id, **PARAMS)


class MeditrustCampus(Adapter):
    name = "meditrust-2027-campus"
    host = "meditrusthealth.m.zhiye.com"
    path = "/yjlist.html"
    ready_endpoints = ("/JobAd/_SearchJobAd",)
    scope_description = "镁信健康独立移动北森 2027 校招 jc=2 全目录；保留源发布日期，排除实习"

    async def harvest(self) -> None:
        observed = await self.session.observed("/JobAd/_SearchJobAd")
        parts = urlsplit(observed["url"])
        check(parts.scheme + "://" + parts.netloc + parts.path == LIST, "镁信校招列表接口改变")
        actual = parse_qs(parts.query, keep_blank_values=True)
        check(
            actual
            == {**{key: [value] for key, value in PARAMS.items()}, "pi": ["1"], "ps": ["10"]},
            "镁信目录存在未知筛选或分页起点改变",
        )
        scope = Scope(name="meditrust-2027-campus")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        first_ids: list[str] | None = None
        for page in range(1, 21):
            response = await self.session.request(query(LIST, **PARAMS, pi=page, ps=10))
            rows = response.get("DataResult")
            if not isinstance(rows, list):
                raise CrawlError("schema_changed", "镁信列表不是数组")
            check(response.get("CurPageSize") == page, "镁信列表返回错误页码")
            check(response.get("RowCount") == len(rows), "镁信本页行数不一致")
            check(len(rows) <= 10, "镁信分页超过公开上限")
            if page == 1:
                first = json.loads(observed["body"])
                first_ids = [str(row["JobAdId"]) for row in first["DataResult"]]
                check(
                    first_ids == [str(row["JobAdId"]) for row in rows],
                    "镁信首屏与遍历第一页岗位不一致",
                )
            if not rows:
                scope.evidence.append(self.session.last_evidence)
                scope.expected = len(seen)
                scope.terminal = True
                break
            check(all(isinstance(row, dict) for row in rows), "镁信列表行结构改变")
            fresh = self.add_page(scope, rows, seen, lambda row: str(row.get("JobAdId", "")))
            list_evidence = self.session.last_evidence
            for row in fresh:
                key = str(row["JobAdId"])
                try:
                    check(row.get("TenantId") == 602524, "镁信列表租户变化")
                    check(row.get("CategoryId") == 2, "镁信列表混入非校园岗位")
                    check(
                        (row.get("KindId"), row.get("KindName")) in {(1, "全职"), (3, "实习")},
                        "镁信职位性质未知",
                    )
                    title = text(row.get("JobAdName"))
                    check(bool(title), "镁信岗位标题为空")
                    date.fromisoformat(row["ToPostDate"])
                    listing = self.job(
                        key,
                        title=title,
                        source_url=detail_page(key),
                        published=row["ToPostDate"],
                        deadline=""
                        if row.get("ToEndDate") == "2222-02-02"
                        else text(row.get("ToEndDate")),
                    )
                    resolved = self.before_detail(
                        "job:" + key, row, scope, listing, evidence=list_evidence
                    )
                    if resolved is not None:
                        self.result.jobs.extend(resolved)
                        continue
                    detail = await self.session.request(
                        query(INFO, adid=key, **{"in": 1}), detail=True
                    )
                    check(
                        detail.get("TenantId") == row["TenantId"]
                        and str(detail.get("JobAdId")) == key
                        and text(detail.get("JobAdName")) == title,
                        "镁信详情身份与列表不一致",
                    )
                    check(
                        detail.get("Kind") == row["KindId"]
                        and text(detail.get("KindName")) == row["KindName"],
                        "镁信详情职位性质不一致",
                    )
                    check(detail.get("PostDateStr") == row["ToPostDate"], "镁信发布日期不一致")
                    check(
                        isinstance(detail.get("DutyStr"), str)
                        and isinstance(detail.get("RequireStr"), str),
                        "镁信详情正文缺失",
                    )
                    end = text(detail.get("EndTimeStr"))
                    check(
                        (row.get("ToEndDate") == "2222-02-02" and end == "-")
                        or end == row.get("ToEndDate"),
                        "镁信截止日期不一致",
                    )
                    job = self.job(
                        key,
                        title=title,
                        work_type=(
                            "实习"
                            if row["KindId"] == 3 or "实习" in title
                            else "校招"
                            if "2027届校招" in title
                            else "非本届校招"
                        ),
                        source_url=detail_page(key),
                        apply_url=detail_page(key),
                        unit=text(detail.get("Department")),
                        location=text(detail.get("LocName")),
                        education=text(detail.get("DegreeStr")),
                        address=text(detail.get("DetailAddress")),
                        category_raw=text(row.get("Class1Name")),
                        duties=text(detail["DutyStr"]),
                        requirements=text(detail["RequireStr"]),
                        published=detail["PostDateStr"],
                        deadline="" if end == "-" else end,
                        field_sources={
                            "duties": "_Info.DutyStr",
                            "requirements": "_Info.RequireStr",
                            "published": "_Info.PostDateStr；核对列表ToPostDate",
                            "deadline": "_Info.EndTimeStr；2222-02-02为未知",
                        },
                    )
                    job.evidence = [list_evidence, self.session.last_evidence]
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember("job:" + key, row, [job])
                except Exception as exc:
                    self.error(exc, key)
                    if isinstance(exc, CrawlError) and exc.code in {
                        "access_denied",
                        "auth_required",
                        "time_budget",
                        "request_budget",
                    }:
                        raise
            if len(rows) < 10:
                # The next empty page is still requested and saved as terminal evidence.
                continue
        check(scope.terminal and scope.expected == scope.unique, "镁信校招分页未闭合")
        check(first_ids is not None, "镁信首屏校验未完成")
