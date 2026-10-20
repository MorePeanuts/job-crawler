"""Two 2027 graduate engineering roles in Inventec Tianjin's HEBUT notice."""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "英业达集团（天津）电子技术有限公司"
HEADER = re.compile(r"^([一二三四])、(.+?)（(\d+)人）$")
DATE = re.compile(r"发布时间：\s*(\d{4}-\d{2}-\d{2})")


def roles(html: str) -> tuple[str, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    panel = soup.select_one(".zpxq")
    check(panel is not None, "英业达高校公告缺失")
    assert panel is not None
    title = panel.select_one(".title")
    employer = panel.select_one('.info a[href="/company/index/id/2310.html"]')
    published = panel.select_one(".info .fb")
    info = panel.select_one(".info")
    contents = panel.select(".content")
    check(
        title is not None
        and employer is not None
        and published is not None
        and info is not None
        and len(contents) == 2,
        "英业达公告主体或版面结构变化",
    )
    assert title is not None and employer is not None and published is not None and info is not None
    check("2027秋季招聘职位" in title.get_text(" ", strip=True), "英业达公告届别变化")
    check(text(employer.get_text()) == f"【{EMPLOYER}】", "英业达高校账号主体错配")
    date = DATE.search(published.get_text(" ", strip=True))
    check(date is not None, "英业达岗位发布时间缺失")
    assert date is not None
    info_text = info.get_text(" ", strip=True)
    location = re.search(r"工作地域：\s*(.*?)\s*职位类别：", info_text)
    education = re.search(r"学历要求：\s*(.*?)\s*招聘人数：", info_text)
    total = re.search(r"招聘人数：\s*(\d+)\s*人", info_text)
    check(
        all(item is not None for item in (location, education, total)),
        "英业达岗位地点、学历或总人数变化",
    )
    assert location is not None and education is not None and total is not None
    check(location[1].strip() == "天津市" and education[1].strip() == "本科", "英业达范围变化")
    overall_majors = text(contents[0].get_text(" ", strip=True))
    check(bool(overall_majors), "英业达整体专业要求缺失")
    rows: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    section = ""
    for p in contents[1].find_all("p", recursive=False):
        value = text(p.get_text(" ", strip=True))
        if not value:
            continue
        header = HEADER.fullmatch(value)
        if header:
            check(
                len(rows) < 2 and header[1] == "一二"[len(rows)],
                "英业达细分岗位序号变化",
            )
            check(
                current is None or bool(current["duties"] and current["requirements"]),
                "英业达岗位段落缺失",
            )
            current = {
                "title": header[2],
                "headcount": header[3],
                "duties": "",
                "requirements": "",
                "majors": overall_majors,
            }
            rows.append(current)
            section = ""
            continue
        check(current is not None, "英业达岗位正文出现在标题前")
        assert current is not None
        if value == "职位描述：":
            section = "duties"
        elif value == "职位要求：":
            section = "requirements"
        else:
            check(bool(section), "英业达岗位正文边界变化")
            current[section] += ("\n" if current[section] else "") + value
    check(
        len(rows) == 2
        and all(row["duties"] and row["requirements"] for row in rows)
        and sum(int(row["headcount"]) for row in rows) == int(total[1]),
        "英业达细分岗位、描述或招聘人数和变化",
    )
    return date[1], rows


class InventecHebut2027(Adapter):
    name = "inventec-hebut-2027"
    host = "career.hebut.edu.cn"
    path = "/correcruit/content/id/79502.html"
    scope_description = "英业达天津公司河北工大 2027 秋季公告中两类明确岗位"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "英业达高校公告未就绪")
        published, rows = roles(await session.page.content())
        evidence = session.last_evidence
        scope = Scope(name="inventec-hebut-2027-79502", expected=len(rows))
        self.result.scopes.append(scope)
        for row in self.add_page(scope, rows, set(), lambda item: item["title"]):
            job = self.job(
                row["title"],
                title=row["title"],
                source_url=self.source.url,
                unit=EMPLOYER,
                location="天津市",
                education="本科",
                work_type="校招",
                duties=row["duties"],
                requirements=row["requirements"] + "\n公告整体专业：" + row["majors"],
                published=published,
                field_sources={
                    "unit": "高校认证账号 2310；英业达集团企业电脑事业群子公司",
                    "title": "职位描述中分段标题与人数",
                    "location": "公告 .info 工作地域",
                    "education": "公告 .info 学历下限；逐岗另有学历描述",
                    "duties": "对应岗位段落的职位描述",
                    "requirements": "对应岗位段落的职位要求及公告整体专业",
                    "published": "公告 .info 发布时间",
                    "deadline": "source_missing:公告未给岗位截止日期",
                    "headcount": f"对应岗位段落 {row['headcount']} 人；两岗合计 15 人",
                },
            )
            job.evidence = [evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
