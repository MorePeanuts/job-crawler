"""Viiyong's server-paged public campus vacancies."""

import re
from typing import Any, Protocol, cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, query
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


class Page(Protocol):
    async def evaluate(self, script: str) -> Any: ...


class PageSession(Protocol):
    page: Page


class ViiyongCampus(Adapter):
    name = "viiyong-campus"
    host = "www.viiyong.com"
    path = "/cn/JobList.aspx?TypeId=10029"
    scope_description = "微容科技官网校园招聘频道的全部服务端分页与公开岗位正文"

    async def harvest(self) -> None:
        scope = Scope(name="campus-type-10029")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        total_pages: int | None = None
        page_num = 1
        while True:
            if page_num > 1:
                await self.session.open(query(f"https://{self.host}{self.path}", current=page_num))
            page = await cast(PageSession, self.session).page.evaluate(
                """() => ({
                  current: Number(document.querySelector('.in-page a.mov.cur')?.textContent),
                  pages: [...document.querySelectorAll('.in-page a.mov')]
                    .map(a => Number(a.textContent)),
                  rows: [...document.querySelectorAll('.join-list ul.hsms > li[hsm="fadeup"]')]
                    .map(li => ({
                      id: li.querySelector('.join-li-btn')?.getAttribute('onclick')
                        ?.match(/AddJob\\((\\d+)/)?.[1] || '',
                      title: li.querySelector('.head h3')?.textContent?.trim() || '',
                      html: li.querySelector('.edit')?.innerHTML || ''
                    }))
                })"""
            )
            check(page["current"] == page_num, "校园职位当前页错配")
            pages = page["pages"]
            check(bool(pages) and pages == list(range(1, max(pages) + 1)), "页码条缺页")
            if total_pages is None:
                total_pages = max(pages)
            check(total_pages == max(pages), "校园职位总页数变化")
            rows = page["rows"]
            check(bool(rows) and len(rows) <= 10, "校园职位页为空或超过页长")
            if page_num < total_pages:
                check(len(rows) == 10, "校园职位非末页不满 10 条")
            scope.evidence.append(self.session.last_evidence)
            for row in rows:
                if row["title"] == "微容科技校招介绍":
                    continue
                key = str(row["id"])
                check(key.isdigit() and key not in seen, "岗位 ID 缺失或分页重复")
                seen.add(key)
                scope.listed += 1
                scope.unique = len(seen)
                try:
                    duties, requirements = self._description(row["html"])
                    check(bool(row["title"] and duties), "岗位标题或正文为空")
                    job = self.job(
                        key,
                        title=row["title"],
                        work_type="校招",
                        source_url=query(f"https://{self.host}{self.path}", current=page_num),
                        duties=duties,
                        requirements=requirements,
                        field_sources={
                            "duties": "校园频道岗位条目正文",
                            "requirements": "校园频道岗位条目正文",
                        },
                    )
                    self.result.jobs.append(job)
                    scope.details += 1
                except Exception as exc:
                    self.error(exc, key)
            if page_num == total_pages:
                scope.expected = len(seen)
                scope.terminal = True
                return
            page_num += 1

    @staticmethod
    def _description(html: str) -> tuple[str, str]:
        body = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        check(bool(body), "校园岗位正文为空")
        markers = list(re.finditer(r"(招聘要求|任职要求|岗位要求|工作职责|岗位职责)\s*[:：]", body))
        if not markers:
            return body, ""
        parts: dict[str, str] = {}
        for index, marker in enumerate(markers):
            end = markers[index + 1].start() if index + 1 < len(markers) else len(body)
            parts[marker.group(1)] = body[marker.end() : end].strip()
        duties = next((parts[x] for x in ("工作职责", "岗位职责") if parts.get(x)), body)
        requirements = next(
            (parts[x] for x in ("招聘要求", "任职要求", "岗位要求") if parts.get(x)), ""
        )
        return duties, requirements
