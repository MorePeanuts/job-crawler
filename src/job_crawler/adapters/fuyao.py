"""Fuyao's public 2027 campus project, limited to group headquarters jobs."""

import re
from typing import cast
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.campaign51 import split_jobinfo
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession


class FuyaoHeadquarters(Adapter):
    name = "fuyao-2027-headquarters"
    host = "job.fuyaogroup.com"
    project_id = "6a752162d3d9c2792c84e535"
    path = (
        "/fuyao/position/index?projectId=6a752162d3d9c2792c84e535&recruitmentType=CAMPUSRECRUITMENT"
    )
    scope_description = "福耀 2027 校招项目全目录；仅标题明确集团总部的本级岗位"

    def rows(self, html: str, expected: int) -> list[dict[str, str]]:
        document = BeautifulSoup(html, "html.parser")
        header = document.find(string=re.compile(r"共\s*\d+\s*个职位"))
        check(bool(header), "福耀职位总数缺失")
        found = re.search(r"共\s*(\d+)\s*个职位", str(header))
        check(bool(found) and int(found.group(1)) == expected, "福耀翻页期间总数变化")
        rows: list[dict[str, str]] = []
        for card in document.select(".position-item[pid]"):
            check(
                card.get("projectid") == self.project_id
                and card.get("recruitment") == "CAMPUSRECRUITMENT",
                "福耀列表项目或招聘类型变化",
            )
            title = card.select_one("h4.title")
            location = card.select_one(".e-city")
            published = card.select_one(".time")
            check(bool(title and location and published), "福耀列表岗位字段缺失")
            assert title is not None and location is not None and published is not None
            date = re.search(r"\d{4}-\d{2}-\d{2}", published.get_text(" ", strip=True))
            check(bool(date), "福耀列表发布日期缺失")
            rows.append(
                {
                    "id": str(card["pid"]),
                    "title": title.get_text(" ", strip=True),
                    "location": location.get_text(" ", strip=True).removeprefix("工作城市："),
                    "published": date.group(0) if date else "",
                }
            )
        return rows

    def detail_url(self, key: str) -> str:
        return "https://job.fuyaogroup.com/fuyao/position/detail?" + urlencode(
            {
                "positionId": key,
                "recruitmentType": "CAMPUSRECRUITMENT",
                "projectId": self.project_id,
                "currentLang": "zh_CN",
            }
        )

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "福耀 2027 校招页面不存在")
        assert session.page is not None
        first_html = await session.page.content()
        document = BeautifulSoup(first_html, "html.parser")
        header = document.find(string=re.compile(r"共\s*\d+\s*个职位"))
        found = re.search(r"共\s*(\d+)\s*个职位", str(header))
        check(bool(found), "福耀校招目录无总数")
        expected = int(found.group(1)) if found else 0
        check(0 < expected <= 1000, "福耀校招目录总数无效")
        sizes = {
            str(item.get("data-pagemax")) for item in document.select(".page-item[data-pagemax]")
        }
        check(sizes == {"15"}, "福耀校招分页大小变化")
        page_count = (expected + 14) // 15
        scope = Scope(name="fuyao-2027-all-jobs", expected=expected)
        self.result.scopes.append(scope)
        seen: set[str] = set()
        headquarters: list[tuple[dict[str, str], str]] = []
        previous_first = ""
        for page in range(1, page_count + 1):
            if page > 1:
                session.consume_request()
                await session.page.locator(f'.page-item[data-pagenum="{page}"]').first.click(
                    timeout=10000
                )
                await session.page.wait_for_function(
                    "id => document.querySelector('.position-item[pid]')?.getAttribute('pid') !== id",
                    arg=previous_first,
                    timeout=10000,
                )
            html = first_html if page == 1 else await session.page.content()
            rows = self.rows(html, expected)
            check(len(rows) == min(15, expected - (page - 1) * 15), "福耀目录分页行数不符")
            previous_first = rows[0]["id"]
            evidence = session.output / "fuyao-pages" / f"{page:02}.json"
            write_json(evidence, {"page": page, "rows": rows, "html": html})
            session.last_evidence = str(evidence)
            for row in self.add_page(scope, rows, seen, lambda item: item["id"]):
                title = row["title"]
                if "集团总部" not in title:
                    scope.skipped_out_of_scope += 1
                    continue
                check("2027届" in title, "福耀总部岗位不属于 2027 校招项目")
                headquarters.append((row, str(evidence)))
        for row, list_evidence in headquarters:
            key = row["id"]
            try:
                url = self.detail_url(key)
                listing = self.job(
                    key,
                    title=row["title"],
                    source_url=url,
                    apply_url=url,
                    location=row["location"],
                    published=row["published"],
                )
                resolved = self.before_detail(
                    f"job:{key}", row, scope, listing, evidence=list_evidence
                )
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                await session.open(url)
                assert session.page is not None
                detail = BeautifulSoup(await session.page.content(), "html.parser")
                title = detail.select_one("h4.name")
                location = detail.select_one(".position-details .city")
                application = detail.select_one("#application[pid]")
                description = detail.select_one(".position-description")
                check(
                    bool(title and location and application and description), "福耀岗位详情字段缺失"
                )
                assert title is not None and location is not None
                assert application is not None and description is not None
                check(title.get_text(" ", strip=True) == row["title"], "福耀详情标题不符")
                check(str(application["pid"]) == key, "福耀详情申请 ID 不符")
                check(location.get_text(" ", strip=True) == row["location"], "福耀详情地点不符")
                duties, requirements = split_jobinfo(str(description))
                check(bool(duties and requirements), "福耀岗位职责或任职要求缺失")
                job = self.job(
                    key,
                    title=row["title"],
                    unit="集团总部",
                    source_url=url,
                    apply_url=url,
                    location=row["location"],
                    duties=duties,
                    requirements=requirements,
                    published=row["published"],
                    field_sources={
                        "duties": "position/detail .position-description:岗位职责",
                        "requirements": "position/detail .position-description:任职要求",
                        "published": "position/index .position-item .time",
                        "deadline": "source_missing",
                    },
                )
                job.evidence = [list_evidence, session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            except Exception as exc:
                self.error(exc, key)
        scope.terminal = True
