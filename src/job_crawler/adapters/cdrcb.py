"""Chengdu Rural Commercial Bank's public 2027 campus catalog."""

import json
import re
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

ROOT = "https://cdrcb2027.zhaopin.com"
API_PATH = "/api/content/get-list"
PROJECT_ID = "ba1e7570defe472ab71a885ab8572ad1"
FORM_ID = "1bb9b16febeb41c483c1266a7bfa682c"


class BankPage(Protocol):
    async def content(self) -> str: ...


class BankSession(Protocol):
    page: BankPage
    last_evidence: str

    async def observed_path(self, path: str) -> dict[str, Any]: ...

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None: ...

    def snapshot(self, label: str, html: str) -> str: ...


def _job_id(url: str) -> str:
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    match = re.fullmatch(r"/job/(CC183402610J[0-9]+)", parts.path)
    check(
        parts.scheme == "https"
        and parts.hostname == "xiaoyuan.zhaopin.com"
        and match is not None
        and query.get("jobSourceType") == ["2"],
        "成都农商银行公开岗位链接身份变化",
    )
    assert match is not None
    return match.group(1)


def _sections(html: str) -> dict[str, str]:
    document = BeautifulSoup(html, "html.parser")
    sections: dict[str, str] = {}
    for header in document.select("h4"):
        title = header.get_text(" ", strip=True)
        parts: list[str] = []
        for sibling in header.next_siblings:
            if getattr(sibling, "name", None) == "h4":
                break
            if hasattr(sibling, "get_text"):
                content = sibling.get_text(" ", strip=True)
                if content:
                    parts.append(content)
        check(title not in sections and bool(parts), "成都农商银行岗位正文分节缺失")
        sections[title] = "\n".join(parts)
    check("招聘条件" in sections, "成都农商银行招聘条件缺失")
    check(
        set(sections) <= {"招聘条件", "具体岗位", "培养目标", "用工方式"},
        "成都农商银行岗位正文新增未知分节",
    )
    return sections


class Cdrcb2027(Adapter):
    name = "cdrcb-2027"
    host = "cdrcb2027.zhaopin.com"
    path = "/jobs/index.html"
    scope_description = "成都农商银行2027年官方活动页全部七类正式校招岗位"
    ready_endpoints = ("https://design-center.zhaopin.com/api/content/get-list",)

    async def harvest(self) -> None:
        session = cast(BankSession, self.session)
        scope = Scope(name="2027-campus")
        self.result.scopes.append(scope)
        page_html = await session.page.content()
        document = BeautifulSoup(page_html, "html.parser")
        check(
            document.title is not None
            and document.title.get_text(" ", strip=True) == "成都农商银行2027校园招聘"
            and "国内普通高等院校的2027年应届毕业生" in document.get_text(" ", strip=True),
            "成都农商银行2027招聘范围变化",
        )
        page_evidence = session.snapshot("cdrcb-jobs", page_html)
        observed = await session.observed_path(API_PATH)
        api_evidence = session.last_evidence
        payload = observed.get("post_data")
        if isinstance(payload, str):
            payload = json.loads(payload)
        check(
            isinstance(payload, dict)
            and payload.get("projectId") == PROJECT_ID
            and payload.get("formId") == FORM_ID
            and payload.get("pageNo") == 1
            and payload.get("pageSize") == 10
            and payload.get("keywords") == ""
            and payload.get("gidField") == "",
            "成都农商银行公开目录请求变更或附带筛选",
        )
        body = observed.get("body")
        check(isinstance(body, str), "成都农商银行公开目录响应缺失")
        assert isinstance(body, str)
        response = json.loads(body)
        data = response.get("data")
        check(
            response.get("code") == 200
            and isinstance(data, dict)
            and data.get("page") == 1
            and data.get("size") == 10
            and data.get("totalPage") == 1
            and isinstance(data.get("total"), int)
            and isinstance(data.get("list"), list)
            and data["total"] == len(data["list"])
            and data["total"] > 0,
            "成都农商银行岗位总数或单页末端变化",
        )
        rows = data["list"]
        scope.expected = data["total"]
        scope.evidence.extend([page_evidence, api_evidence])

        await session.open(ROOT + "/liuc/index.html")
        process_html = await session.page.content()
        process = BeautifulSoup(process_html, "html.parser")
        check(
            process.title is not None
            and process.title.get_text(" ", strip=True) == "成都农商银行2027校园招聘"
            and "报名截止时间为2026年10月25日" in process.get_text(" ", strip=True),
            "成都农商银行报名截止日变化",
        )
        deadline_evidence = session.snapshot("cdrcb-deadline", process_html)
        scope.evidence.append(deadline_evidence)

        seen: set[str] = set()
        seen_content: set[str] = set()
        for position, row in enumerate(rows, 1):
            try:
                check(isinstance(row, dict), "成都农商银行岗位对象结构变化")
                content = row.get("jsonContent")
                check(
                    row.get("status") == 1
                    and row.get("projectId") == PROJECT_ID
                    and row.get("formId") == FORM_ID
                    and row.get("sortno") == position
                    and isinstance(row.get("contentId"), str)
                    and isinstance(content, dict),
                    "成都农商银行岗位身份或排序变化",
                )
                title = content.get("title")
                url = content.get("url")
                html = content.get("content")
                check(
                    isinstance(title, str)
                    and title.startswith(f"{position}.")
                    and isinstance(url, str)
                    and isinstance(html, str)
                    and bool(html),
                    "成都农商银行岗位标题、链接或正文缺失",
                )
                job_id = _job_id(url)
                content_id = row["contentId"]
                check(content_id not in seen_content, "成都农商银行重复内容 ID")
                seen_content.add(content_id)
                check(job_id not in seen, "成都农商银行重复岗位 ID")
                seen.add(job_id)
                scope.listed += 1
                scope.unique += 1
                sections = _sections(html)
                requirements = sections["招聘条件"]
                degree = (
                    "硕士"
                    if "硕士研究生及以上" in requirements
                    else "本科"
                    if "本科及以上" in requirements
                    else ""
                )
                check(bool(degree), "成都农商银行最低学历语义变化")
                display_title = re.sub(r"^[0-9]+\.", "", title).strip()
                unit = "总行" if display_title.startswith("总行") else "本行分支机构"
                job = self.job(
                    job_id,
                    title=display_title,
                    unit=unit,
                    batch="2027届校园招聘",
                    education=degree,
                    requirements=requirements,
                    deadline="2026-10-25",
                    source_url=url,
                    apply_url=url,
                    field_sources={
                        "title": "get-list.jsonContent.title",
                        "unit": "get-list.jsonContent.title",
                        "education": "get-list.jsonContent.content 招聘条件",
                        "requirements": "get-list.jsonContent.content 招聘条件",
                        "deadline": "/liuc/index.html 报名截止时间",
                        "duties": "source_missing:活动页无独立岗位职责",
                        "location": "source_missing:活动页无逐岗位工作地点",
                        "published": "source_missing:CMS创建和更新日期不是岗位发布日期",
                    },
                )
                job.evidence = [page_evidence, api_evidence, deadline_evidence]
                self.result.jobs.append(job)
                scope.details += 1
            except Exception as exc:
                self.error(exc, str(position))
        scope.terminal = scope.unique == scope.expected and not self.result.issues
