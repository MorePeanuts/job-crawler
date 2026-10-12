"""Hangzhou Steel's verified two-page static campus campaign."""

from typing import Protocol, cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


class Page(Protocol):
    async def content(self) -> str: ...


class PageSession(Protocol):
    page: Page


class Hzsteel(Adapter):
    name = "hzsteel-static"
    host = "campus.51job.com"
    path = "/hzsteel/hiring.html"
    scope_description = "杭钢入口的岗位介绍链接所指单页全部 .cos 卡片；无公开发布时间"

    async def harvest(self) -> None:
        page = cast(PageSession, self.session).page
        entry = BeautifulSoup(await page.content(), "html.parser")
        links = [
            anchor
            for anchor in entry.select("a[href]")
            if anchor.get_text(" ", strip=True) == "岗位介绍"
        ]
        check(len(links) == 1, "杭钢入口缺少唯一岗位介绍链接")
        target = urljoin(self.source.url, str(links[0].get("href", "")))
        check(
            urlsplit(target).hostname == self.host
            and urlsplit(target).path == "/hzsteel/process.html",
            "杭钢岗位介绍导航目标变化",
        )
        entry_evidence = self.session.last_evidence
        await self.session.open(target)
        document = BeautifulSoup(await page.content(), "html.parser")
        cards = []
        for item in document.select(".cos"):
            title = item.select_one(".jobname")
            if title is not None and title.get_text(" ", strip=True):
                cards.append(item)
                continue
            info = item.select_one(".jobinfo")
            apply = item.select_one("a.apply[href]")
            check(
                (info is None or not info.get_text(" ", strip=True))
                and (apply is None or not str(apply.get("href", "")).startswith("https://")),
                "杭钢出现无标题但含岗位内容的卡片",
            )
        check(bool(cards), "杭钢岗位页没有可验证卡片")
        scope = Scope(name="hzsteel-process-page", expected=len(cards))
        scope.evidence.extend([entry_evidence, self.session.last_evidence])
        self.result.scopes.append(scope)
        seen: set[str] = set()
        for card in cards:
            scope.listed += 1
            title_node = card.select_one(".jobname")
            info = card.select_one(".jobinfo")
            apply = card.select_one("a.apply[href]")
            check(
                title_node is not None and info is not None and apply is not None,
                "杭钢卡片缺少标题、介绍或申请链接",
            )
            assert title_node is not None and info is not None and apply is not None
            title = title_node.get_text(" ", strip=True)
            requirements = info.get_text("\n", strip=True)
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
                "杭钢卡片正文或申请链接无效",
            )
            job_id = ids[0]
            check(job_id not in seen, "杭钢岗位申请 ID 重复")
            seen.add(job_id)
            scope.unique += 1
            job = self.job(
                job_id,
                title=title,
                requirements=requirements,
                source_url=apply_url,
                apply_url=apply_url,
                field_sources={
                    "requirements": "process.html .cos .jobinfo",
                    "duties": "source_missing:无独立岗位职责",
                    "location": "source_missing:无岗位地点",
                    "published": "source_missing:无公开发布日期",
                },
            )
            job.evidence = [entry_evidence, self.session.last_evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
