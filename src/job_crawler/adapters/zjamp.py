"""Employer-submitted 2027 campus announcement on Zhejiang University careers."""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.adapters.smic import HtmlSession
from job_crawler.models import Scope


def parse_announcement(html: str) -> list[dict[str, str | int]]:
    soup = BeautifulSoup(html, "html.parser")
    page = soup.get_text(" ", strip=True)
    check("浙农集团股份有限公司2027届校园招聘" in page, "浙农公告主体或届别变化")
    tables = [
        table for table in soup.select("table") if "热招岗位" in table.get_text(" ", strip=True)
    ]
    check(len(tables) == 1, "浙农公告岗位表缺失或重复")
    table = tables[0]
    rows = table.select("tr")
    check(len(rows) == 6, "浙农公告岗位行数变化")
    check(
        [re.sub(r"\s+", "", cell.get_text(" ", strip=True)) for cell in rows[0].select("td,th")]
        == ["热招岗位", "岗位职责及要求"],
        "浙农公告表头变化",
    )
    result: list[dict[str, str | int]] = []
    names: set[str] = set()
    for row in rows[1:]:
        cells = row.select("td")
        check(len(cells) == 2, "浙农公告岗位表列数变化")
        label = cells[0].get_text(" ", strip=True)
        match = re.fullmatch(r"\s*(.+?)\s*[（(]\s*(\d+)\s*人\s*[）)]\s*", label)
        check(match is not None, "浙农岗位名额缺失")
        assert match is not None
        name = match.group(1).strip()
        body = cells[1].get_text("\n", strip=True)
        check(bool(name and body) and name not in names, "浙农岗位重复或描述缺失")
        names.add(name)
        result.append({"name": name, "headcount": int(match.group(2)), "body": body})
    check(sum(int(row["headcount"]) for row in result) == 29, "浙农公告人数合计变化")
    check(re.search(r"\b29\s*人\b", page) is not None, "浙农页面摘要人数变化")
    return result


class ZjampCampus(Adapter):
    name = "zjamp-2027-announcement"
    host = "www.career.zju.edu.cn"
    path = "/jyxt/sczp/zpztgl/ckZpgwXq.zf?zpxxbh=5DB02B741D05BCA6E0653A68DD0E9B18"
    scope_description = (
        "浙农集团2027届校招公告五类热招岗位，涵盖总部及成员企业；公告未给逐岗法人和发布日期"
    )

    async def harvest(self) -> None:
        session = cast(HtmlSession, self.session)
        rows = parse_announcement(await session.page.content())
        scope = Scope(name="zjamp-2027-announcement", expected=len(rows))
        self.result.scopes.append(scope)
        seen: set[str] = set()
        for row in self.add_page(scope, rows, seen, lambda item: str(item["name"])):
            self.result.jobs.append(
                self.job(
                    str(row["name"]),
                    title=str(row["name"]),
                    source_url=self.source.url,
                    work_type="校招",
                    requirements=str(row["body"]),
                    field_sources={
                        "requirements": "浙江大学就业服务平台：2027 校招公告岗位表原文职责及要求",
                        "duties": "source_missing:公告将职责和要求混列",
                        "published": "source_missing:仅有公告发布时间",
                        "deadline": "source_missing:页面摘要日期语义未明",
                        "unit": "source_missing:公告涵盖总部及成员企业未逐岗指定",
                    },
                )
            )
            scope.details += 1
        scope.terminal = True
