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


def listing(row: dict[str, Any], *, allow_locationless: bool = False) -> str:
    path = row.get("externalPath", "")
    pattern = r"/job/(?:[^/?#]+/)?[^/?#]+" if allow_locationless else r"/job/[^/?#]+/[^/?#]+"
    check(
        isinstance(path, str) and re.fullmatch(pattern, path) is not None,
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
    time_types = {"Full time", "Part time"}
    allow_locationless = False
    allow_missing_country = False

    def listing_key(self, row: dict[str, Any]) -> str:
        return listing(row, allow_locationless=self.allow_locationless)

    def body(self, html: str) -> tuple[str, str]:
        return description(html)

    def kind(self, title: str, requirements: str, time_type: str) -> str:
        return recruitment_type(title, words(requirements), time_type)

    @property
    def api(self) -> str:
        return f"https://{self.host}/wday/cxs/{self.tenant}/{self.site}"

    def parse_detail(self, data: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
        info = data.get("jobPostingInfo")
        check(isinstance(info, dict), "Workday详情业务对象缺失")
        assert isinstance(info, dict)
        key = self.listing_key(row)
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
        check(info.get("timeType") in self.time_types, "Workday时间类型变化")
        raw = info.get("jobDescription")
        check(isinstance(raw, str), "Workday正文类型变化")
        assert isinstance(raw, str)
        duties, requirements = self.body(raw)
        country = info.get("country", {"descriptor": ""} if self.allow_missing_country else {})
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
            "work_type": self.kind(info["title"], requirements, info["timeType"]),
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
                first = [self.listing_key(row) for row in rows]
            for row in self.add_page(scope, rows, seen, self.listing_key):
                key = self.listing_key(row)
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
                    and [self.listing_key(row) for row in refreshed.get("jobPostings", [])]
                    == first,
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


FWD_BACKGROUND_LINKS = {
    "http://www.fwd.com",
    "http://www.fwd.com/",
    "https://www.fwd.com.hk/",
    "http://www.insurance.gov.ph",
    "https://talocity.ai/gdpr/",
    "https://www.fwd.com.my/",
    "http://www.fwd.com.vn",
    "https://www.fwd.com.kh/en/",
}


class FwdWorkday(WorkdayPublicJobs):
    name = "fwd-workday"
    tenant = "fwd"
    site = "FWDcareersite"
    host = "fwd.wd3.myworkdayjobs.com"
    path = "/zh-CN/FWDcareersite/"
    ready_endpoints = ("/wday/cxs/fwd/FWDcareersite/jobs",)
    time_types = {"全职"}
    scope_description = "富卫Workday全部国家、公司、部门；仅明确正式应届，排除实习和已录用者登记"

    def body(self, html: str) -> tuple[str, str]:
        doc = BeautifulSoup(html, "html.parser")
        check(not doc.select("img,iframe,object,embed,video"), "富卫正文含未展开媒体")
        check(
            all(a.get("href") in FWD_BACKGROUND_LINKS for a in doc.select("a[href]")),
            "富卫新增正文链接需核对",
        )
        lines = doc.get_text("\n", strip=True).splitlines()
        check(bool(lines) and lines[0] == "About FWD Group", "富卫正文主体变化")
        if "Privacy Notice" in lines:
            lines = lines[: lines.index("Privacy Notice")]
        starts = [
            n
            for n, line in enumerate(lines)
            if re.fullmatch(
                r"Job Summary|Job Purpose|PURPOSE|The Job|Key Responsibilities|KEY ACCOUNTABILITIES|KEY ACCOUNTAIBILITIES",
                words(line).rstrip(":"),
                re.I,
            )
        ]
        if starts:
            lines = lines[min(starts) :]
        check(len("\n".join(lines)) > 100, "富卫正文缺失")
        for n, line in enumerate(lines):
            if re.fullmatch(
                r"The Person|QUALIFICATIONS(?: / EXPERIENCE)?|Skills & Experience Required|Job Requirements|Requirements?|Key Qualifications",
                words(line).rstrip(":"),
                re.I,
            ):
                return "\n".join(lines[:n]).strip(), "\n".join(lines[n + 1 :]).strip()
        return "", "\n".join(lines)

    def kind(self, title: str, requirements: str, time_type: str) -> str:
        if re.fullmatch(r"【\d{4}年度新卒】内定者 登録用", title):
            check("への内定、誠におめでとうございます" in requirements, "富卫内定者登记正文变化")
            return "已录用者登记"
        check("新卒" not in title, "富卫新增日文应届项目需核对")
        return recruitment_type(title, words(requirements), time_type)


HKEX_FUNCTIONS = (
    "https://www.hkexgroup.com/About-HKEX/Organisation/Management?sc_lang=en"
    "#E5AAA8AE291446B2B49CCFFBA1F68D1A"
)


class HkexWorkday(WorkdayPublicJobs):
    name = "hkex-workday"
    allow_locationless = True
    allow_missing_country = True
    tenant = "hkex"
    site = "HKEXCareerPage"
    host = "hkex.wd3.myworkdayjobs.com"
    path = "/zh-CN/HKEXCareerPage"
    ready_endpoints = ("/wday/cxs/hkex/HKEXCareerPage/jobs",)
    scope_description = (
        "港交所Workday全部国家/公司公开目录；含明确应届混合岗位及Graduate Associate，排除实习"
    )

    def body(self, html: str) -> tuple[str, str]:
        doc = BeautifulSoup(html, "html.parser")
        check(not doc.select("img,iframe,object,embed,video"), "港交所正文含未展开媒体")
        check(
            all(
                a.get("href") in {HKEX_FUNCTIONS, "mailto:earlycareers@hkex.com.hk"}
                for a in doc.select("a[href]")
            ),
            "港交所新增正文外链需核对",
        )
        lines = doc.get_text("\n", strip=True).splitlines()
        check(len("\n".join(lines)) > 100, "港交所正文为空")
        starts = [
            n for n, line in enumerate(lines) if words(line) in {"Job Summary:", "Job Duties:"}
        ]
        if starts:
            lines = lines[min(starts) :]
        tails = [
            n
            for n, line in enumerate(lines)
            if line.startswith("HKEX is committed as an Equal Opportunity Employer.")
            or words(line) == "Location:"
        ]
        if tails:
            lines = lines[: min(tails)]
        for n, line in enumerate(lines):
            if re.fullmatch(
                r"(?:Job |Key |Essential )?Requirements?|Qualifications(?: & Experience)?|Required Skills & Experience|Academic and Professional Qualifications Required|We are looking for candidates who",
                words(line).rstrip(":"),
                re.I,
            ):
                return "\n".join(lines[:n]).strip(), "\n".join(lines[n + 1 :]).strip()
        return "", "\n".join(lines)
