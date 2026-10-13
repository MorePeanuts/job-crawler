"""New China Life's public server-rendered graduate list with inline descriptions."""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.adapters.smic import HtmlSession
from job_crawler.models import Scope


def parse_nci(html: str) -> tuple[int, int, int, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    content = soup.get_text(" ", strip=True)
    total = re.search(r"共\s*(\d+)\s*条记录", content)
    current = re.search(r"当前第\s*(\d+)\s*/\s*(\d+)\s*页", content)
    check(total is not None and current is not None, "新华人寿缺少分页证据")
    assert total is not None and current is not None
    count, page, pages = int(total[1]), int(current[1]), int(current[2])
    check(pages == max(1, (count + 49) // 50), "新华人寿分页大小或总数改变")
    rows = []
    for a in soup.select("a.ljyp[jobadid]"):
        card = a.find_parent("li")
        check(card is not None, "新华人寿岗位容器缺失")
        assert card is not None
        fields = card.select("h1.zwlblit > span")
        check(len(fields) == 5, "新华人寿目录字段数改变")
        sections = {}
        for section in card.select(".zwms"):
            label = section.select_one(".zwmsl")
            value = section.select_one(".zwmsr")
            check(label is not None and value is not None, "新华人寿正文缺失")
            assert label is not None and value is not None
            sections[label.get_text(strip=True).rstrip("：:")] = value.get_text("\n", strip=True)
        check("职位描述" in sections and "任职要求" in sections, "新华人寿正文标题改变")
        rows.append(
            {
                "id": str(a["jobadid"]),
                "title": str(fields[0].get("title") or fields[0].get_text(strip=True)),
                "unit": str(fields[1].get("title") or fields[1].get_text(strip=True)),
                "location": str(fields[2].get("title") or fields[2].get_text(strip=True)),
                "published": fields[4].get_text(strip=True),
                "duties": sections["职位描述"],
                "requirements": sections["任职要求"],
            }
        )
    check(len(rows) == min(50, max(0, count - (page - 1) * 50)), "新华人寿页岗位数不符")
    return count, page, pages, rows


class NciCampus(Adapter):
    name = "nci-campus-html"
    host = "nci.zhiye.com"
    path = "/xyzp?class=2"
    scope_description = "新华人寿校园招聘 class=2 全目录；旧北森每页50条内嵌完整正文"

    async def harvest(self) -> None:
        session = cast(HtmlSession, self.session)
        scope = Scope(name="nci-campus-class-2")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            url = f"https://{self.host}/xyzp/?class=2&PageIndex={page}"
            html = await session.page.content() if page == 1 else await session.request_html(url)
            count, current, pages, parsed = parse_nci(html)
            check(current == page, "新华人寿返回错误页码")
            if scope.expected is None:
                scope.expected = count
            check(count == scope.expected, "新华人寿目录总数变化")
            rows = self.add_page(scope, parsed, seen, lambda r: r["id"])
            for row in rows:
                self.result.jobs.append(
                    self.job(
                        row["id"],
                        title=row["title"],
                        unit=row["unit"],
                        location=row["location"],
                        published=row["published"],
                        duties=row["duties"],
                        requirements=row["requirements"],
                        source_url=url,
                        field_sources={
                            "duties": "zwms:职位描述",
                            "requirements": "zwms:任职要求",
                            "location": "目录地点 span.title 全文",
                            "published": "目录发布时间",
                            "deadline": "source_missing",
                        },
                    )
                )
                scope.details += 1
            if page >= pages:
                check(scope.unique == count, "新华人寿唯一岗位数不符")
                scope.terminal = True
                break
            page += 1
