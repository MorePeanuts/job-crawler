"""Astronergy's public campus category with embedded full vacancy text."""

import re
from typing import Protocol, cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


class Page(Protocol):
    async def content(self) -> str: ...


class PageSession(Protocol):
    page: Page


class AstronergyCampus(Adapter):
    name = "astronergy-campus"
    host = "astronergy.com.cn"
    path = "/join/index/mode/campus.html"
    scope_description = "正泰新能官网校园招聘频道完整公开条目及展开正文"

    async def harvest(self) -> None:
        soup = BeautifulSoup(await cast(PageSession, self.session).page.content(), "html.parser")
        cards = soup.select(".join-list > .item")
        check(bool(cards), "校园招聘目录为空或尚未加载")
        more = soup.select_one("a.load-more")
        check(
            more is not None
            and bool(re.search(r"display\s*:\s*none", str(more.get("style") or ""))),
            "校园目录还有未加载页",
        )
        scope = Scope(name="campus-mode", expected=len(cards))
        self.result.scopes.append(scope)
        seen: set[str] = set()
        for card in cards:
            title_node = card.select_one(".info .name[id]")
            type_node = card.select_one(".info .type")
            location_node = card.select_one(".info .address")
            text_node = card.select_one(".erify .content .txt")
            check(
                title_node is not None and type_node is not None and text_node is not None,
                "校园岗位结构改变",
            )
            assert title_node is not None and type_node is not None and text_node is not None
            key = str(title_node.get("id") or "")
            check(
                bool(re.fullmatch(r"[0-9a-f-]{36}", key)) and key not in seen,
                "校园岗位 ID 无效或重复",
            )
            seen.add(key)
            scope.listed += 1
            scope.unique = len(seen)
            check("校招" in type_node.get_text(" ", strip=True), "校园类别混入其他职位")
            title = title_node.get_text(" ", strip=True)
            body = text_node.get_text("\n", strip=True)
            check(bool(title and body), "校园岗位标题或正文为空")
            check("任职要求：" in body, "校园岗位缺少任职要求段落")
            duties, requirements = body.split("任职要求：", 1)
            check(bool(duties.strip() and requirements.strip()), "校园岗位职责或要求为空")
            job = self.job(
                key,
                title=title,
                work_type="实习" if "实习" in title else "校招",
                source_url=f"https://{self.host}{self.path}",
                location=location_node.get_text(" ", strip=True) if location_node else "",
                category_raw=type_node.get_text(" ", strip=True),
                duties=duties.strip(),
                requirements=requirements.strip(),
                field_sources={
                    "duties": "campus .join-list .erify .content .txt",
                    "requirements": "campus .join-list .erify .content .txt",
                    "published": "source_missing; site date is update time",
                },
            )
            self.result.jobs.append(job)
            scope.details += 1
        scope.evidence.append(self.session.last_evidence)
        scope.terminal = True
