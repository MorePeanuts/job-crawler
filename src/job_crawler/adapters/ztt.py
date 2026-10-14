"""Verified static 2027 Zhongtian Technology campus positions."""

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


def label_value(info: Tag, label: str) -> str:
    for span in info.select("span.label"):
        if span.get_text(" ", strip=True).rstrip("：:") != label:
            continue
        fragments: list[str] = []
        for sibling in span.next_siblings:
            if isinstance(sibling, Tag):
                classes = sibling.get("class")
                if isinstance(classes, list) and "label" in classes:
                    break
            fragments.append(str(sibling))
        return BeautifulSoup("".join(fragments), "html.parser").get_text("\n", strip=True)
    return ""


class ZttCampus(Adapter):
    name = "ztt-campus"
    host = "campus.51job.com"
    path = "/ztt/positions.html"
    scope_description = "中天科技集团 2027 届静态招聘岗位页全部独立申请 ID；源未公开逐岗职责和日期"

    async def harvest(self) -> None:
        document = BeautifulSoup(
            await cast(PageSession, self.session).page.content(), "html.parser"
        )
        check("招聘岗位" in document.get_text(" ", strip=True), "中天职位导航缺失")
        cards = document.select(".job-list > .job-item")
        check(bool(cards), "中天职位卡片为空或结构变化")
        scope = Scope(name="ztt-2027-static", expected=len(cards))
        self.result.scopes.append(scope)
        scope.evidence.append(self.session.last_evidence)
        seen: set[str] = set()
        for card in cards:
            scope.listed += 1
            title_node = card.select_one(".job-hd")
            info = card.select_one(".job-info")
            apply = card.select_one("a.job-apply[href]")
            check(
                title_node is not None and info is not None and apply is not None,
                "中天岗位卡片缺少字段",
            )
            assert title_node is not None and info is not None and apply is not None
            title = title_node.get_text(" ", strip=True)
            apply_url = str(apply.get("href", ""))
            parsed = urlsplit(apply_url)
            query = parse_qs(parsed.query)
            ids = query.get("jobid", [])
            check(
                bool(title)
                and parsed.scheme == "https"
                and parsed.hostname == "xyz.51job.com"
                and parsed.path == "/external/apply.aspx"
                and len(ids) == 1
                and ids[0].isdigit()
                and query.get("ctmid") == ["8928843"],
                "中天岗位申请链接或活动 ID 无效",
            )
            job_id = ids[0]
            check(job_id not in seen, "中天申请岗位 ID 重复")
            seen.add(job_id)
            scope.unique += 1
            requirements = label_value(info, "应聘条件")
            specialty = label_value(info, "需求专业")
            location = label_value(info, "工作地点")
            check(
                "2027年毕业的本科及以上学历" in requirements and bool(specialty and location),
                "中天 2027 届条件或专业地点字段变化",
            )
            job = self.job(
                job_id,
                title=title,
                location=location,
                education="本科及以上",
                requirements=f"{requirements}\n需求专业：{specialty}",
                source_url=apply_url,
                apply_url=apply_url,
                field_sources={
                    "location": "job-item.job-info:工作地点",
                    "education": "job-item.job-info:应聘条件（2027 年本科及以上）",
                    "requirements": "job-item.job-info:应聘条件、需求专业",
                    "duties": "source_missing:岗位类别卡片无逐岗职责",
                    "published": "source_missing:无逐岗公开发布日期",
                    "deadline": "source_missing:无逐岗公开截止日",
                },
            )
            job.evidence = [self.session.last_evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
