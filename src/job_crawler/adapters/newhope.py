"""New Hope's server-rendered campus catalog with inline job details."""

import re
from typing import Protocol, cast

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

URL = "https://newhope.zhiye.com/xzzw"


class Page(Protocol):
    async def content(self) -> str: ...


class HtmlSession(Protocol):
    page: Page
    last_evidence: str


def catalog(html: str) -> tuple[int, list[dict[str, str]]]:
    document = BeautifulSoup(html, "html.parser")
    match = re.search(r"共\s*(\d+)\s*条记录", document.get_text(" ", strip=True))
    check(match is not None, "新希望目录缺少岗位总数")
    assert match is not None
    rows: list[dict[str, str]] = []
    for item in document.select("li:has(> h2 > span.pl25)"):
        heading = item.select_one("h2")
        apply = item.select_one("a[jobadid]")
        check(isinstance(heading, Tag) and isinstance(apply, Tag), "新希望岗位结构改变")
        assert isinstance(heading, Tag) and isinstance(apply, Tag)
        cells = heading.select("span")
        check(len(cells) >= 5, "新希望目录列数改变")
        sections: dict[str, str] = {}
        for section in item.select(".zwlbbm h3"):
            following = section.find_next_sibling("p")
            if isinstance(following, Tag):
                sections[section.get_text(" ", strip=True).strip("【】")] = following.get_text(
                    "\n", strip=True
                )
        attributes: dict[str, str] = {}
        for attribute in item.select(".zwlbbt span"):
            label = attribute.get_text(" ", strip=True)
            value = attribute.select_one("b")
            if isinstance(value, Tag) and "：" in label:
                attributes[label.split("：", 1)[0]] = value.get_text(" ", strip=True)
        check(
            bool(sections.get("岗位职责") and sections.get("任职要求")),
            "新希望岗位缺少职责或要求",
        )
        key = str(apply.get("jobadid", ""))
        check(key.isdigit(), "新希望岗位缺少招聘 ID")
        rows.append(
            {
                "id": key,
                "title": cells[0].get_text(" ", strip=True),
                "category": cells[1].get_text(" ", strip=True),
                "location": attributes.get("工作地点") or cells[3].get_text(" ", strip=True),
                "unit": attributes.get("需求部门", ""),
                "published": cells[4].get_text(" ", strip=True),
                "duties": sections["岗位职责"],
                "requirements": sections["任职要求"],
            }
        )
    return int(match[1]), rows


class NewHopeCampus(Adapter):
    name = "newhope-inline-campus"
    host = "newhope.zhiye.com"
    path = "/xzzw"
    scope_description = "新希望校招 /xzzw 内嵌详情的完整列表"

    async def harvest(self) -> None:
        session = cast(HtmlSession, self.session)
        scope = Scope(name="newhope-campus")
        self.result.scopes.append(scope)
        expected, parsed = catalog(await session.page.content())
        scope.expected = expected
        rows = self.add_page(scope, parsed, set(), lambda row: row["id"])
        check(scope.unique == expected, "新希望目录数量与岗位明细数不符")
        for row in rows:
            job = self.job(
                row["id"],
                title=row["title"],
                unit=row["unit"],
                category_raw=row["category"],
                location=row["location"],
                duties=row["duties"],
                requirements=row["requirements"],
                published=row["published"],
                source_url=URL,
                apply_url=URL,
                field_sources={
                    "duties": "xzzw:岗位职责",
                    "requirements": "xzzw:任职要求",
                    "published": "xzzw:发布时间",
                },
            )
            self.result.jobs.append(job)
            scope.details += 1
            self.remember(f"job:{row['id']}", row, [job])
        scope.terminal = True
