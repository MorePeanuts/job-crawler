"""The two headquarters trainee tracks in Shccig's 2027 official notice."""

import re
from datetime import date
from typing import Protocol, cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

COMPANY = "陕西煤业化工集团有限责任公司"
PATH = "/index/Article/index.html?cid=97&id=1429903"
APPLY_URL = "https://webhr.shccig.com/webhrN2-zp/"
TITLE = COMPANY + " 2027年度管理培训生招聘简章"
ROLE_PATTERN = re.compile(r"^(\d+)\.([^。]+岗)$")


class ArticlePage(Protocol):
    async def content(self) -> str: ...


class ArticleSession(Protocol):
    page: ArticlePage
    last_evidence: str


def _section(lines: list[str], start: str, end: str) -> list[str]:
    check(start in lines and end in lines, "陕煤管培生公告章节缺失")
    begin = lines.index(start)
    finish = lines.index(end)
    check(begin < finish, "陕煤管培生公告章节顺序变化")
    return lines[begin + 1 : finish]


def _date(raw: str, label: str) -> str:
    chinese = re.fullmatch(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", raw)
    if chinese:
        raw = f"{int(chinese[1]):04d}-{int(chinese[2]):02d}-{int(chinese[3]):02d}"
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise ValueError(f"陕煤管培生{label}格式变化") from exc


class ShccigHeadquartersTrainees(Adapter):
    name = "shccig-headquarters-trainees"
    host = "www.shccig.com"
    path = PATH
    scope_description = "陕煤集团2027管培生官方公告；集团总部统一招录的两类岗位"

    async def harvest(self) -> None:
        session = cast(ArticleSession, self.session)
        html = await session.page.content()
        doc = BeautifulSoup(html, "html.parser")
        heading = doc.select_one(".article > h1")
        meta = doc.select(".article-tishi > span")
        content = doc.select_one(".article-con")
        check(
            heading is not None
            and heading.get_text(" ", strip=True) == TITLE
            and len(meta) >= 2
            and meta[0].get_text(strip=True) == "集团公司人力资源部"
            and content is not None,
            "陕煤管培生公告标题、作者或正文变化",
        )
        assert content is not None
        published = _date(meta[1].get_text(strip=True), "发布日期")
        lines = [
            value
            for node in content.find_all("p", recursive=False)
            if (value := node.get_text(" ", strip=True))
        ]
        overview = _section(lines, "一、管培生计划简介", "二、招聘对象")
        check(
            any("由集团总部统一招录、统一培养、统一管理、统一调配" in s for s in overview),
            "陕煤管培生集团总部统一招录证据缺失",
        )
        role_lines = _section(lines, "三、招聘岗位及专业", "四、应聘基本条件")
        check(len(role_lines) == 8, "陕煤管培生岗位目录结构或数量变化")
        common = _section(lines, "四、应聘基本条件", "五、报名方式")
        check(bool(common), "陕煤管培生共同任职条件缺失")
        signup = _section(lines, "五、报名方式", "六、招聘流程")
        deadline_marker = "2.报名截止时间"
        check(
            deadline_marker in signup and signup.index(deadline_marker) + 1 < len(signup),
            "陕煤管培生报名截止日缺失",
        )
        deadline = _date(signup[signup.index(deadline_marker) + 1], "截止日")
        scope = Scope(name="2027-headquarters-trainees", expected=2)
        scope.evidence.append(session.last_evidence)
        self.result.scopes.append(scope)
        for index in range(0, len(role_lines), 4):
            segment = role_lines[index : index + 4]
            match = ROLE_PATTERN.fullmatch(segment[0])
            check(
                match is not None
                and match[1] == str(index // 4 + 1)
                and segment[1].startswith("学历要求：")
                and segment[2].startswith("招聘人数：")
                and segment[3].startswith("专业要求："),
                "陕煤管培生岗位编号或字段变化",
            )
            assert match is not None
            scope.listed += 1
            scope.unique += 1
            if deadline < self.as_of.date().isoformat():
                scope.skipped_expired += 1
                continue
            job = self.job(
                "2027-mt-" + match[1],
                title=match[2],
                unit=COMPANY,
                batch="2027年度管理培训生",
                education=segment[1].removeprefix("学历要求："),
                requirements="\n".join([segment[3], *common]),
                published=published,
                deadline=deadline,
                source_url=self.source.url,
                apply_url=APPLY_URL,
                field_sources={
                    "unit": "公告一：集团总部统一招录、统一培养、统一管理、统一调配",
                    "title": "公告三：招聘岗位及专业",
                    "education": "公告三：逐岗学历要求",
                    "requirements": "公告三：逐岗专业要求 + 公告四：共同条件",
                    "location": "公告未列逐岗工作地点，保留空值",
                    "duties": "公告未列逐岗具体职责，保留空值",
                    "published": "公告元数据时间",
                    "deadline": "公告五：报名截止时间",
                },
            )
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
