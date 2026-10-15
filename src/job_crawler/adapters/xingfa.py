"""Xingfa 2027 employer notice mirrored by China University of Geosciences."""

import re
from typing import cast

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.adapters.smic import HtmlSession
from job_crawler.models import Scope


def parse_notice(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    page = soup.get_text(" ", strip=True)
    check("湖北兴发化工集团股份有限公司" in page, "兴发校招雇主主体变化")
    check("兴发集团2027届校园人才招聘简章" in page, "兴发公告届别变化")
    check("秋季校园招聘时间为2026年9月至11月" in re.sub(r"\s+", "", page), "秋招时段变化")
    headings = [
        node for node in soup.select(".aContent h3") if "需求岗位" in node.get_text("", strip=True)
    ]
    check(len(headings) == 1, "兴发需求岗位章节缺失或重复")
    heading = headings[0]
    sections: list[dict[str, str]] = []
    expected_numbers = "一二三四五"
    current: dict[str, str] | None = None
    for node in heading.next_siblings:
        if not isinstance(node, Tag):
            continue
        label = re.sub(r"[\s\u200c]+", "", node.get_text(" ", strip=True))
        if label.startswith("三、其他重点福利"):
            break
        match = re.fullmatch(r"（([一二三四五])）(.+类)", label)
        if match:
            check(len(sections) < 5, "兴发公告出现额外岗位分节")
            check(match.group(1) == expected_numbers[len(sections)], "兴发岗位分节编号变化")
            current = {"name": match.group(2)}
            sections.append(current)
            continue
        if current is None:
            continue
        for prefix, key in (
            ("需求专业：", "requirements"),
            ("学历层次：", "education"),
            ("工作地点：", "location"),
        ):
            if label.startswith(prefix):
                check(key not in current, "兴发岗位分节字段重复")
                current[key] = label[len(prefix) :]
                break
    check(len(sections) == 5, "兴发需求岗位五类未闭合")
    check(
        all(
            all(row.get(key) for key in ("name", "requirements", "education", "location"))
            for row in sections
        ),
        "兴发岗位专业、学历或地点缺失",
    )
    check(len({row["name"] for row in sections}) == 5, "兴发岗位类名称重复")
    return sections


class XingfaCampus(Adapter):
    name = "xingfa-2027-notice"
    host = "cug.91wllm.cn"
    path = "/teachin/view/id/251585"
    scope_description = "兴发股份提交至中国地质大学的2027届校招公告五类需求岗位，秋招2026年9至11月"

    async def harvest(self) -> None:
        session = cast(HtmlSession, self.session)
        rows = parse_notice(await session.page.content())
        scope = Scope(name="xingfa-2027-five-categories", expected=5)
        self.result.scopes.append(scope)
        seen: set[str] = set()
        for row in self.add_page(scope, rows, seen, lambda item: item["name"]):
            self.result.jobs.append(
                self.job(
                    row["name"],
                    title=row["name"],
                    source_url=self.source.url,
                    work_type="校招",
                    location=row["location"],
                    education=row["education"],
                    requirements="需求专业：" + row["requirements"],
                    field_sources={
                        "requirements": "2027 届校招简章需求岗位.需求专业",
                        "education": "2027 届校招简章需求岗位.学历层次",
                        "location": "2027 届校招简章需求岗位.工作地点",
                        "duties": "source_missing:公告无逐类岗位职责",
                        "published": "source_missing:宣讲日期不是岗位发布日期",
                        "deadline": "source_missing:秋招时段不等于逐岗截止日期",
                    },
                )
            )
            scope.details += 1
        scope.terminal = True
