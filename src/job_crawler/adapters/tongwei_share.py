"""通威股份在南开大学 2027 届简章明确列出的八个岗位。"""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "通威股份有限公司"
DATE = re.compile(r"发布时间：\s*(\d{4}-\d{2}-\d{2})")


def roster(html: str) -> tuple[str, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    check("通威股份 2027届校园招聘" in page_text, "通威股份 2027 届公告标题改变")
    check("通威股份有限公司由通威集团控股" in page_text, "通威股份与集团关系缺失")
    check("光伏商务部" in page_text and "光伏技术部" in page_text, "通威股份招聘部门改变")
    date_match = DATE.search(page_text)
    check(date_match is not None, "通威股份公告发布时间缺失")
    assert date_match is not None
    paragraphs = [p for p in soup.select(".zpnr p") if text(p.get_text()).startswith("热招岗位：")]
    check(len(paragraphs) == 2, "通威股份热招岗位段落数量改变")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, (paragraph, department, delimiter, major_label) in enumerate(
        zip(
            paragraphs,
            ("光伏商务部", "光伏技术部"),
            ("/", "、"),
            ("优选专业：", "匹配专业："),
            strict=True,
        )
    ):
        raw = text(paragraph.get_text()).removeprefix("热招岗位：")
        titles = [part.strip() for part in raw.split(delimiter)]
        check(len(titles) == 4 and all(titles), "通威股份部门岗位数量或分隔符改变")
        major_node = paragraph.find_next_sibling("p")
        check(major_node is not None, "通威股份部门专业要求缺失")
        assert major_node is not None
        major_text = text(major_node.get_text())
        check(major_text.startswith(major_label), "通威股份部门专业要求对应关系改变")
        majors = major_text.removeprefix(major_label).strip()
        check(bool(majors), "通威股份部门专业要求为空")
        for title in titles:
            key = f"{index + 1}:{title}"
            check(key not in seen, "通威股份公告岗位重复")
            seen.add(key)
            result.append({"id": key, "title": title, "department": department, "majors": majors})
    check(len(result) == 8, "通威股份公告当届岗位总数改变")
    return date_match.group(1), result


class TongweiShare2027(Adapter):
    name = "tongwei-share-nankai-2027"
    host = "career.nankai.edu.cn"
    path = "/correcruit/content/id/118918.html"
    scope_description = "通威集团控股通威股份在南开大学2027届简章列出的光伏商务部、技术部八岗"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "南开大学通威股份校园简章未就绪")
        published, rows = roster(await session.page.content())
        evidence = self.session.last_evidence
        scope = Scope(name="tongwei-share-2027-nankai", expected=len(rows))
        self.result.scopes.append(scope)
        for row in self.add_page(scope, rows, set(), lambda item: item["id"]):
            job = self.job(
                row["id"],
                title=row["title"],
                work_type="校招",
                source_url=self.source.url,
                unit=EMPLOYER,
                requirements=row["majors"],
                published=published,
                field_sources={
                    "unit": "南开大学简章：通威股份有限公司由通威集团控股",
                    "title": f"{row['department']} 热招岗位段落",
                    "requirements": f"{row['department']} 专业要求段落",
                    "published": "南开大学招聘简章发布时间",
                    "education": "source_missing:整体学历范围不能推断逐岗最低学历",
                    "location": "source_missing:公告整体/类别地点不作为逐岗精确地点",
                    "duties": "source_missing:公告未给逐岗职责",
                    "deadline": "source_missing:公告未给招聘截止日期",
                    "headcount": "公告整体招聘人数 60；不按人数拆分",
                },
            )
            job.evidence = [evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
