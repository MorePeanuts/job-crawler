"""One verified static 51job campaign page; no platform-wide assumptions."""

from typing import Protocol, cast
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


class Page(Protocol):
    async def content(self) -> str: ...


class PageSession(Protocol):
    page: Page


def labeled_value(desc: Tag, label: str) -> str:
    for heading in desc.select(".job-label"):
        if heading.get_text(" ", strip=True).rstrip("：:") != label:
            continue
        fragments: list[str] = []
        for sibling in heading.next_siblings:
            if isinstance(sibling, Tag):
                classes = sibling.get("class")
                if isinstance(classes, list) and ("job-label" in classes or "job-btn" in classes):
                    break
            fragments.append(str(sibling))
        return BeautifulSoup("".join(fragments), "html.parser").get_text("\n", strip=True)
    return ""


class Wtmec(Adapter):
    name = "wtmec-static"
    host = "campus.51job.com"
    path = "/wtmec/job.html"
    scope_description = "文晔活动页 job.html 中所有 .job-item 静态岗位卡片；无分页和公开发布日期"

    async def harvest(self) -> None:
        html = await cast(PageSession, self.session).page.content()
        document = BeautifulSoup(html, "html.parser")
        check("招聘岗位" in document.get_text(" ", strip=True), "文晔页面缺少招聘岗位导航")
        cards = document.select(".job-item")
        check(bool(cards), "文晔岗位卡片为空或结构变化")
        scope = Scope(name="wtmec-static-page", expected=len(cards))
        self.result.scopes.append(scope)
        scope.evidence.append(self.session.last_evidence)
        seen: set[str] = set()
        for card in cards:
            scope.listed += 1
            title_node = card.select_one(".job-name")
            desc = card.select_one(".job-desc")
            apply = card.select_one("a.job-btn[href]")
            check(
                title_node is not None and desc is not None and apply is not None,
                "文晔岗位卡片缺少标题、正文或申请链接",
            )
            assert title_node is not None and desc is not None and apply is not None
            title = title_node.get_text(" ", strip=True)
            apply_url = str(apply.get("href", ""))
            parsed = urlsplit(apply_url)
            ids = parse_qs(parsed.query).get("jobid", [])
            check(
                bool(title)
                and parsed.scheme == "https"
                and parsed.hostname == "xyz.51job.com"
                and parsed.path == "/external/apply.aspx"
                and len(ids) == 1
                and ids[0].isdigit(),
                "文晔岗位标题或公开申请链接无效",
            )
            job_id = ids[0]
            check(job_id not in seen, "文晔岗位申请 ID 重复")
            seen.add(job_id)
            scope.unique += 1
            duties = labeled_value(desc, "岗位职责")
            requirements = labeled_value(desc, "任职要求")
            location = labeled_value(desc, "工作地点")
            check(bool(duties and requirements and location), "文晔岗位字段标签或正文变化")
            job = self.job(
                job_id,
                title=title,
                location=location,
                duties=duties,
                requirements=requirements,
                source_url=apply_url,
                apply_url=apply_url,
                field_sources={
                    "location": "job-item.job-desc:工作地点",
                    "duties": "job-item.job-desc:岗位职责",
                    "requirements": "job-item.job-desc:任职要求",
                    "published": "source_missing:无公开发布日期",
                },
            )
            job.evidence = [self.session.last_evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
