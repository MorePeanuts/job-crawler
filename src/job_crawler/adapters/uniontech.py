"""UnionTech's public recruitment cards and matching in-page detail panels."""

import re
from typing import Protocol, cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Issue, Scope


class Page(Protocol):
    async def content(self) -> str: ...


class PageSession(Protocol):
    page: Page


class UnionTechCampus(Adapter):
    name = "uniontech-campus"
    host = "uniontech.com"
    path = "/Recruitment.html"
    scope_description = "统信软件官网完整招聘卡片目录和对应详情；列表与详情均为校园招聘"

    async def harvest(self) -> None:
        html = await cast(PageSession, self.session).page.content()
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("#pos .zp-item")
        check(bool(cards), "招聘卡片目录为空")
        scope = Scope(name="public-recruitment-cards", expected=len(cards))
        self.result.scopes.append(scope)
        rows = []
        for card in cards:
            match = re.fullmatch(r"pageNew\((\d+)\)", str(card.get("onclick") or ""))
            check(match is not None, "岗位卡片 ID 缺失")
            title_node = card.select_one("span")
            kind_node = card.select_one("em")
            status_node = card.select_one(".zp-cont p")
            check(title_node is not None and kind_node is not None, "岗位卡片结构改变")
            assert match is not None and title_node is not None and kind_node is not None
            rows.append(
                {
                    "id": match.group(1),
                    "title": title_node.get_text(" ", strip=True),
                    "kind": kind_node.get_text(" ", strip=True),
                    "status": status_node.get_text(" ", strip=True) if status_node else "",
                }
            )
        seen: set[str] = set()
        self.add_page(scope, rows, seen, lambda row: row["id"])
        for row in rows:
            key = row["id"]
            if "校园招聘" not in row["kind"]:
                scope.skipped_out_of_scope += 1
                continue
            panel = soup.find(id=key)
            check(panel is not None, f"岗位 {key} 缺少对应详情")
            assert panel is not None
            detail_title = panel.select_one(".zp-head span")
            detail_kind = panel.select_one(".zp-head p")
            duties_node = panel.find(id=f"info{key}")
            requirements_node = panel.find(id=f"info{key}_1")
            check(detail_title is not None and detail_kind is not None, "校园详情结构改变")
            assert detail_title is not None and detail_kind is not None
            check(detail_title.get_text(" ", strip=True) == row["title"], "校园详情标题错配")
            detail_type = detail_kind.get_text(" ", strip=True)
            if "校园招聘" not in detail_type:
                scope.skipped_out_of_scope += 1
                self.result.warnings.append(
                    Issue(
                        code="recruitment_type_conflict",
                        message="岗位列表标校园招聘，详情标社会招聘，按详情排除",
                        source_id=self.source.source_id,
                        job_key=key,
                        url=self.source.url,
                    )
                )
                continue
            if row["status"] != "招聘中":
                scope.skipped_closed += 1
                continue
            check(duties_node is not None and requirements_node is not None, "校园正文缺失")
            assert duties_node is not None and requirements_node is not None
            duties = duties_node.get_text("\n", strip=True)
            requirements = requirements_node.get_text("\n", strip=True)
            check(bool(duties and requirements), "校园正文为空")
            pieces = [part.strip() for part in detail_type.split("｜")]
            job = self.job(
                key,
                title=row["title"],
                work_type="校招",
                source_url=f"https://{self.host}{self.path}",
                location=pieces[0] if pieces else "",
                category_raw=pieces[1] if len(pieces) > 1 else "",
                duties=duties,
                requirements=requirements,
                field_sources={
                    "duties": f"Recruitment.html#info{key}",
                    "requirements": f"Recruitment.html#info{key}_1",
                    "published": "source_missing",
                },
            )
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
