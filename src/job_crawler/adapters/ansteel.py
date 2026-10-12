"""Enumerate every company tab on Ansteel's public static campaign page."""

import asyncio
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Issue, Scope


class Page(Protocol):
    async def evaluate(self, script: str, arg: Any = None) -> Any: ...

    async def content(self) -> str: ...


class TabSession(Protocol):
    page: Page

    def snapshot(self, label: str, html: str) -> str: ...


def labeled_line(body: str, label: str) -> str:
    for line in body.splitlines():
        if line.startswith(label + "：") or line.startswith(label + ":"):
            return line[len(label) + 1 :].strip()
    return ""


class Ansteel(Adapter):
    name = "ansteel-static"
    host = "campus.51job.com"
    path = "/ansteel2026/job.html"
    scope_description = "鞍钢活动页全部招聘企业选项，每选项的静态 .jobs 卡片及申请 ID"

    async def harvest(self) -> None:
        session = cast(TabSession, self.session)
        page = session.page
        tabs = await page.evaluate(
            "() => [...document.querySelectorAll('.jobtype > div')].map(x => x.innerText.trim())"
        )
        check(
            isinstance(tabs, list)
            and bool(tabs)
            and all(isinstance(name, str) and name for name in tabs)
            and len(tabs) == len(set(tabs)),
            "鞍钢招聘企业选项缺失或重复",
        )
        assert isinstance(tabs, list)
        seen: set[str] = set()
        for index, name in enumerate(tabs):
            await page.evaluate(
                "index => document.querySelectorAll('.jobtype > div')[index].click()", index
            )
            await asyncio.sleep(0.1)
            active = await page.evaluate(
                "() => document.querySelector('.jobtype > div.on')?.innerText.trim()"
            )
            check(active == name, f"鞍钢招聘企业切换失败: {name}")
            html = await page.content()
            document = BeautifulSoup(html, "html.parser")
            check("招聘岗位" in document.get_text(" ", strip=True), "鞍钢岗位页导航变化")
            cards = document.select(".joblist .jobs")
            if not cards:
                check(
                    "暂无岗位" in document.get_text(" ", strip=True),
                    f"鞍钢 {name} 目录为空且无明确空状态",
                )
            evidence = session.snapshot(f"unit-{index + 1:02d}", html)
            scope = Scope(name=f"unit-{index + 1:02d}-{name}", expected=len(cards))
            scope.evidence.append(evidence)
            self.result.scopes.append(scope)
            for card in cards:
                scope.listed += 1
                title_node = card.select_one(".jobtit span")
                info = card.select_one(".jobinfo")
                apply = card.select_one('a[href*="external/apply.aspx"]')
                check(
                    title_node is not None and info is not None and apply is not None,
                    f"鞍钢 {name} 岗位卡片缺少标题、资格或申请链接",
                )
                assert title_node is not None and info is not None and apply is not None
                title = title_node.get_text(" ", strip=True)
                info_copy = BeautifulSoup(str(info), "html.parser")
                for anchor in info_copy.select("a"):
                    anchor.decompose()
                requirements = info_copy.get_text("\n", strip=True)
                apply_url = str(apply.get("href", ""))
                parsed = urlsplit(apply_url)
                ids = parse_qs(parsed.query).get("jobid", [])
                check(
                    bool(title and requirements)
                    and parsed.scheme == "https"
                    and parsed.hostname == "xyz.51job.com"
                    and parsed.path == "/external/apply.aspx"
                    and len(ids) == 1
                    and ids[0].isdigit(),
                    f"鞍钢 {name} 岗位正文或申请链接无效",
                )
                job_id = ids[0]
                check(job_id not in seen, f"鞍钢岗位申请 ID 跨企业重复: {job_id}")
                seen.add(job_id)
                scope.unique += 1
                education = labeled_line(requirements, "学历要求")
                location = labeled_line(requirements, "工作地点")
                for field, value in (("学历要求", education), ("工作地点", location)):
                    if not value:
                        self.result.warnings.append(
                            Issue(
                                code="field_missing",
                                message=f"鞍钢 {name} 岗位缺少可识别的{field}标签",
                                source_id=self.source.source_id,
                                job_key=job_id,
                                url=apply_url,
                            )
                        )
                job = self.job(
                    job_id,
                    title=title,
                    unit=name,
                    education=education,
                    location=location,
                    requirements=requirements,
                    source_url=apply_url,
                    apply_url=apply_url,
                    field_sources={
                        "unit": ".jobtype > div.on",
                        "education": (
                            ".jobs .jobinfo:学历要求"
                            if education
                            else "source_missing:学历要求标签"
                        ),
                        "location": (
                            ".jobs .jobinfo:工作地点" if location else "source_missing:工作地点标签"
                        ),
                        "requirements": ".jobs .jobinfo",
                        "duties": "source_missing:无独立岗位职责",
                        "published": "source_missing:无公开发布日期",
                    },
                )
                job.evidence = [evidence]
                self.result.jobs.append(job)
                scope.details += 1
            scope.terminal = True
