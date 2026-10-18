"""Observed public Workday CXS catalog; tenants are explicitly registered."""

import json
import re
from datetime import date
from typing import Any
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import CrawlError

BASE_QUERY = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}


def words(value: str) -> str:
    return " ".join(value.split())


def listing(row: dict[str, Any]) -> str:
    path = row.get("externalPath", "")
    check(
        isinstance(path, str) and re.fullmatch(r"/job/[^/?#]+/[^/?#]+", path) is not None,
        "Workday岗位路径结构变化",
    )
    check(isinstance(row.get("title"), str) and bool(row["title"].strip()), "Workday标题缺失")
    check(isinstance(row.get("bulletFields"), list), "Workday业务编号列表缺失")
    return path.rsplit("/", 1)[-1]


def absolute_date(value: object) -> str:
    if value in (None, ""):
        return ""
    check(isinstance(value, str), "Workday日期类型变化")
    assert isinstance(value, str)
    check(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None, "Workday非ISO日期")
    return date.fromisoformat(value).isoformat()


def description(html: str) -> tuple[str, str]:
    doc = BeautifulSoup(html, "html.parser")
    check(not doc.select("a[href],img,iframe,object,embed,video"), "Workday正文含未展开链接媒体")
    lines = doc.get_text("\n", strip=True).splitlines()
    # Melco puts the requisition/title in the first paragraph, even when the body is empty.
    if lines and re.match(r"^REQ\d+\b", lines[0]):
        lines = lines[1:]
    check(len("\n".join(lines).strip()) > 30, "Workday正文空白，无法判断招聘范围")
    for n, line in enumerate(lines):
        if re.fullmatch(
            r"(?:QUALIFICATIONS|JOB REQUIREMENTS|Requirements|Key Qualifications)\s*[.:]?",
            words(line),
            re.I,
        ):
            return "\n".join(lines[:n]).strip(), "\n".join(lines[n + 1 :]).strip()
    # Keep unsplit source material in one field, never fabricate two distinct sections.
    return "", "\n".join(lines)


def recruitment_type(title: str, requirements: str, time_type: str) -> str:
    if re.search(r"\bintern(?:ship)?\b|实习|實習", title, re.I):
        return "实习"
    if time_type == "Part time" or re.search(r"\b(?:temporary|part[- ]time)\b", title, re.I):
        return "临时岗位"
    if re.search(r"\bgraduate (?:trainee|associate|programme|program)\b", title, re.I) or re.search(
        r"\b(?:fresh|recent|new) (?:university |college )?graduates?\b|应届|應屆|校招",
        requirements,
        re.I,
    ):
        return "校招"
    check(
        not re.search(
            r"campus recruit|school leaver|graduate programme|graduate program|毕业生|畢業生",
            title + "\n" + requirements,
            re.I,
        ),
        "Workday新增毕业生表述需核对",
    )
    return "未明确校招"


class WorkdayPublicJobs(Adapter):
    tenant = ""
    site = ""

    @property
    def api(self) -> str:
        return f"https://{self.host}/wday/cxs/{self.tenant}/{self.site}"

    def parse_detail(self, data: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
        info = data.get("jobPostingInfo")
        check(isinstance(info, dict), "Workday详情业务对象缺失")
        assert isinstance(info, dict)
        key = listing(row)
        check(
            bool(info.get("id"))
            and info.get("jobPostingId") == key
            and info.get("jobReqId") in row["bulletFields"]
            and info.get("jobPostingSiteId") == self.site
            and words(info.get("title", "")) == words(row["title"]),
            "Workday详情身份、标题或租户错配",
        )
        url = info.get("externalUrl", "")
        parts = urlsplit(url)
        check(
            parts.scheme == "https"
            and parts.netloc == self.host
            and parts.path == "/" + self.site + row["externalPath"]
            and not parts.query
            and not parts.fragment,
            "Workday详情公开路径错配",
        )
        check(
            type(info.get("canApply")) is bool and type(info.get("posted")) is bool,
            "Workday开放状态缺失",
        )
        check(info.get("timeType") in {"Full time", "Part time"}, "Workday时间类型变化")
        raw = info.get("jobDescription")
        check(isinstance(raw, str), "Workday正文类型变化")
        assert isinstance(raw, str)
        duties, requirements = description(raw)
        country = info.get("country", {})
        check(
            isinstance(country, dict) and isinstance(country.get("descriptor"), str),
            "Workday国家字段缺失",
        )
        location = info.get("location", "")
        additional = info.get("additionalLocations", [])
        check(
            isinstance(location, str)
            and isinstance(additional, list)
            and all(isinstance(x, str) for x in additional),
            "Workday地点结构变化",
        )
        locations = list(dict.fromkeys([location, *additional]))
        organization = data.get("hiringOrganization") or {}
        check(isinstance(organization, dict), "Workday招聘单位结构变化")
        return {
            "title": info["title"],
            "source_url": url,
            "unit": organization.get("name") or "",
            "location": "、".join(x for x in [country["descriptor"], *locations] if x),
            "duties": duties,
            "requirements": requirements,
            "published": absolute_date(info.get("startDate")),
            "deadline": absolute_date(info.get("endDate")),
            "closed": not info["canApply"] or not info["posted"],
            "work_type": recruitment_type(info["title"], requirements, info["timeType"]),
            "field_sources": {
                "published": "jobPostingInfo.startDate；不使用相对postedOn",
                "deadline": "jobPostingInfo.endDate；日粒度原值",
                "location": "country.descriptor + location + additionalLocations；未推定街道",
                "unit": "hiringOrganization.name；空值不推断",
                "duties": "明确资格标题之前原文；无法分节则留空",
                "requirements": "资格分节；无明确标题时保留完整原文",
                "work_type": "明确应届表述；实习、兼职排除；经验与应届资格原文并存不删改",
            },
        }

    async def harvest(self) -> None:
        observed = await self.session.observed(self.api + "/jobs")
        check(observed["url"] == self.api + "/jobs", "Workday列表租户路径错配")
        check(json.loads(observed["post_data"]) == BASE_QUERY, "Workday入口存在未验证筛选")
        scope = Scope(name=f"workday-{self.tenant}-{self.site}-all")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        first: list[str] = []
        for offset in range(0, 5000, 20):
            response = await self.session.request(
                self.api + "/jobs", payload={**BASE_QUERY, "offset": offset}
            )
            total = response.get("total")
            if offset == 0:
                check(type(total) is int and 0 < total <= 5000, "Workday零目录未实证或总数超预算")
                scope.expected = total
            check(total in (0, scope.expected) and type(total) is int, "Workday总数变化")
            assert scope.expected is not None
            rows = response.get("jobPostings")
            check(
                isinstance(rows, list) and len(rows) == min(20, scope.expected - offset),
                "Workday目录短页或缺行",
            )
            assert isinstance(rows, list)
            evidence = self.session.last_evidence
            if offset == 0:
                first = [listing(row) for row in rows]
            for row in self.add_page(scope, rows, seen, listing):
                key = listing(row)
                try:
                    reused = self.before_detail("job:" + key, row, scope, evidence=evidence)
                    if reused is not None:
                        self.result.jobs.extend(reused)
                        continue
                    data = await self.session.request(self.api + "/job/" + key)
                    job = self.job(key, **self.parse_detail(data, row))
                    job.evidence = [evidence, self.session.last_evidence]
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember("job:" + key, row, [job])
                except Exception as exc:
                    self.error(exc, key)
                    if isinstance(exc, CrawlError) and exc.code in {
                        "access_denied",
                        "request_budget",
                        "time_budget",
                    }:
                        raise
            if scope.unique == scope.expected:
                refreshed = await self.session.request(self.api + "/jobs", payload=BASE_QUERY)
                check(
                    refreshed.get("total") == scope.expected
                    and [listing(row) for row in refreshed.get("jobPostings", [])] == first,
                    "Workday遍历期间首页或总数变化",
                )
                scope.evidence.append(self.session.last_evidence)
                scope.terminal = True
                return
        raise ValueError("Workday未在预算内闭合目录")


class MelcoWorkday(WorkdayPublicJobs):
    name = "melco-workday"
    tenant = "melcoresorts"
    site = "career"
    host = "melcoresorts.wd3.myworkdayjobs.com"
    path = "/en-US/career"
    ready_endpoints = ("/wday/cxs/melcoresorts/career/jobs",)
    scope_description = "新濠博亚Workday全部国家地区公开目录；仅明确正式应届，缺正文报错"
