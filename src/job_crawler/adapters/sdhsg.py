"""Shandong Hi-speed's public campus directory and frontend-defined details."""

import json
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession, CrawlError

ROOT = "https://zhaopin.sdhsg.com"
API = ROOT + "/sdhsghr"
LIST = API + "/hr/job/weblist"
QUERY = {
    "recruitType": "1",
    "startTime": "",
    "endTime": "",
    "areaId": "",
    "orgId": "",
    "jobType": "",
    "specialty": "",
    "page": "1",
    "limit": "10",
    "status": "1",
    "sidx": "",
    "order": "desc",
}


def query(observed: dict[str, Any]) -> dict[str, str]:
    parts = urlsplit(observed["url"])
    check(parts.scheme + "://" + parts.netloc + parts.path == LIST, "山东高速目录接口改变")
    values = parse_qs(parts.query, keep_blank_values=True)
    values.pop("_t", None)
    check(values == {k: [v] for k, v in QUERY.items()}, "山东高速校园目录存在局部筛选或参数变化")
    return dict(QUERY)


def fields(item: dict[str, Any]) -> dict[str, str]:
    unit = text(item.get("orgName"))
    parent = text(item.get("orgNameParent"))
    if parent and parent != unit and parent != "山东高速集团有限公司":
        unit = f"{parent} / {unit}"
    location = (
        text(item.get("areaInfo"))
        if str(item.get("areaId")) == "991414"
        else "/".join(
            value
            for value in (
                text(item.get("provinceName")),
                text(item.get("areaName")),
            )
            if value
        )
    )
    if str(item.get("district")) == "1" and text(item.get("districtInfo")):
        location = " ".join(filter(None, (location, text(item["districtInfo"]))))
    return {
        "title": text(item.get("name")),
        "unit": unit,
        "location": location,
        "education": text(item.get("educationName")),
        "category_raw": text(item.get("jobTypeName")),
        "deadline": text(item.get("endTime")),
    }


def requirements(item: dict[str, Any]) -> str:
    parts = [text(item.get("jobRequirement"))]
    for key, label in (
        ("educationName", "学历要求"),
        ("specialtyValue", "专业"),
        ("experience", "工作经验要求（年及以上）"),
        ("minAge", "最小年龄（周岁）"),
        ("maxAge", "最大年龄（周岁）"),
        ("computeAgeDate", "年龄计算截止日期"),
        ("politicalName", "政治面貌"),
        ("exam", "考试要求"),
    ):
        value = text(item.get(key))
        if value and value != "0":
            parts.append(f"{label}：{value}")
    return "\n".join(filter(None, parts))


class SdhsgCampus(Adapter):
    name = "sdhsg-campus"
    host = "zhaopin.sdhsg.com"
    path = "/#/centralizedRecruitment"
    ready_endpoints = (LIST,)
    scope_description = "山东高速集团校园recruitType=1/status=1全单位公开目录；不含社会和内部招聘"

    async def harvest(self) -> None:
        observed = await self.session.observed(LIST)
        params = query(observed)
        response = json.loads(observed["body"])
        scope = Scope(name="sdhsg-campus-all-organizations")
        self.result.scopes.append(scope)
        page = 1
        seen: set[str] = set()
        while True:
            check(response.get("code") == 0, "山东高速目录业务失败")
            data = response["page"]
            expected = data.get("totalCount")
            rows = data.get("list")
            check(
                type(expected) is int
                and expected >= 0
                and isinstance(rows, list)
                and data.get("currPage") == page
                and data.get("pageSize") == 10
                and data.get("totalPage") == (expected + 9) // 10,
                "山东高速分页结构或计数异常",
            )
            assert isinstance(expected, int) and isinstance(rows, list)
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "山东高速翻页期间总数变化")
            check(len(rows) == min(10, expected - len(seen)), "山东高速分页缺行或提前为空")
            listing_evidence = self.session.last_evidence
            scope.evidence.append(listing_evidence)
            if expected == 0:
                html = await cast(BrowserSession, self.session).page.content()
                content = text(html)
                check(
                    all(value in content for value in ("校招职位名称", "暂无数据", "共 0 条")),
                    "山东高速零目录缺少校园页面证据",
                )
            for row in self.add_page(scope, rows, seen, lambda r: str(r["id"])):
                key = str(row["id"])
                try:
                    check(
                        key.isdigit() and bool(text(row.get("name")) and text(row.get("orgName"))),
                        "山东高速岗位身份缺失",
                    )
                    check(str(row.get("status")) == "1", "山东高速目录混入非在招岗位")
                    url = ROOT + "/#/jobInfo?" + urlencode({"jobid": key})
                    draft = self.job(key, **fields(row), source_url=url, work_type="校招")
                    draft.field_sources = {
                        "published": "source_missing:开始时间startTime是报名时间，并非发布日期",
                        "deadline": "queryJob.job.endTime（终止时间）",
                        "duties": "queryJob.job.jobExplain（岗位职责）",
                        "requirements": "queryJob.job.jobRequirement及结构化资格字段",
                        "location": "queryJob.job省市/areaInfo/districtInfo，遵循公开页面",
                    }
                    draft.evidence = [listing_evidence]
                    reused = self.before_detail(
                        "job:" + key, row, scope, draft, evidence=listing_evidence
                    )
                    if reused is not None:
                        self.result.jobs.extend(reused)
                        continue
                    result = await self.session.request(
                        API + "/hr/job/queryJob?" + urlencode({"id": key}), detail=True
                    )
                    draft.evidence.append(self.session.last_evidence)
                    check(
                        result.get("code") == 0 and isinstance(result.get("job"), dict),
                        "山东高速详情业务失败",
                    )
                    item = result["job"]
                    check(
                        str(item.get("id")) == key
                        and text(item.get("name")) == text(row["name"])
                        and text(item.get("orgName")) == text(row["orgName"])
                        and str(item.get("recruitType")) == "1",
                        "山东高速详情身份、单位或校园类型不符",
                    )
                    status = str(item.get("status"))
                    check(status in {"0", "1"}, "山东高速详情为预览或未知状态")
                    if status == "0":
                        draft.visible = False
                        draft.detail_mode = "listing_only"
                        scope.skipped_closed += 1
                    else:
                        attachments = await self.session.request(
                            API + "/hr/upload/getUploadFile?" + urlencode({"jobId": key}),
                            detail=True,
                        )
                        draft.evidence.append(self.session.last_evidence)
                        check(
                            attachments.get("code") == 0 and attachments.get("uploadList") == [],
                            "山东高速附件未处理或附件查询失败",
                        )
                        for name in ("jobExplain", "jobRequirement"):
                            check(name in item, "山东高速详情缺少正文结构")
                            body = BeautifulSoup(str(item[name] or ""), "html.parser")
                            check(
                                not body.select("img,a[href],iframe,object,embed"),
                                "山东高速正文含未处理附件",
                            )
                        check(
                            bool(text(item["jobExplain"]) or text(item["jobRequirement"])),
                            "山东高速详情正文为空",
                        )
                        for name, value in fields(item).items():
                            setattr(draft, name, value)
                        draft.duties = text(item["jobExplain"])
                        draft.requirements = requirements(item)
                        scope.details += 1
                    self.result.jobs.append(draft)
                    self.remember("job:" + key, row, [draft])
                except Exception as exc:
                    self.error(exc, key)
                    if isinstance(exc, CrawlError) and exc.code in {
                        "access_denied",
                        "request_budget",
                        "time_budget",
                    }:
                        raise
            if len(seen) == expected:
                scope.terminal = True
                break
            page += 1
            response = await self.session.request(
                LIST + "?" + urlencode({**params, "page": str(page)})
            )
