"""天山铝业在河北工业大学就业站公开的校招生全目录。"""

import re
from typing import cast
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "天山铝业集团股份有限公司"
PROFILE_PATH = "/company/index/id/19244.html"
DETAIL_RE = re.compile(r"/correcruit/content/id/(\d+)\.html")


def profile_jobs(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    name = soup.select_one(".company_index > .p1")
    check(name is not None and text(name.get_text()) == EMPLOYER, "天山铝业高校企业账户变化")
    links = soup.select(".lizw[href]")
    check(bool(links), "天山铝业高校目录未证明有岗位或明确零岗位")
    check(
        not any("下一页" in anchor.get_text(" ", strip=True) for anchor in soup.select("a")),
        "天山铝业高校目录出现未支持的分页",
    )
    rows: list[dict[str, str]] = []
    for anchor in links:
        path = urlsplit(str(anchor.get("href") or "")).path
        match = DETAIL_RE.fullmatch(path)
        title = anchor.select_one(".zw_title .p1")
        published = anchor.select_one(".zw_title .p2")
        check(
            match is not None and title is not None and published is not None,
            "天山铝业目录行结构改变",
        )
        assert match is not None and title is not None and published is not None
        title_text = text(title.get_text())
        check("校招生" in title_text, "天山铝业高校目录混入未确认校园岗位")
        rows.append(
            {
                "id": match.group(1),
                "title": title_text,
                "published": text(published.get_text()),
                "url": urljoin("https://career.hebut.edu.cn", path),
            }
        )
    check(len({row["id"] for row in rows}) == len(rows), "天山铝业高校目录重复岗位 ID")
    return rows


def detail_job(html: str, listed: dict[str, str]) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    panel = soup.select_one(".zpxq")
    check(panel is not None, "天山铝业高校岗位详情缺失")
    assert panel is not None
    title_node = panel.select_one(".title")
    employer = panel.select_one(f'.info a[href="{PROFILE_PATH}"]')
    published_node = panel.select_one(".info .fb")
    info = panel.select_one(".info")
    sections = panel.select(".content")
    check(
        title_node is not None
        and employer is not None
        and published_node is not None
        and info is not None
        and bool(sections),
        "天山铝业高校岗位详情字段缺失",
    )
    assert title_node is not None and employer is not None and published_node is not None
    assert info is not None
    check(text(employer.get_text()) == f"【{EMPLOYER}】", "天山铝业高校岗位详情主体改变")
    salary = title_node.select_one(".gongzi")
    if salary is not None:
        salary.decompose()
    title = text(title_node.get_text(" ", strip=True))
    check(title == listed["title"], "天山铝业高校目录与详情标题不一致")
    published_match = re.search(
        r"发布时间：\s*(\d{4}-\d{2}-\d{2})", published_node.get_text(" ", strip=True)
    )
    check(
        published_match is not None and published_match.group(1) == listed["published"],
        "天山铝业高校目录与详情发布时间不一致",
    )
    assert published_match is not None
    info_text = info.get_text(" ", strip=True)
    location = re.search(r"工作地域：\s*(.*?)\s*职位类别：", info_text)
    category = re.search(r"职位类别：\s*(.*?)\s*学历要求：", info_text)
    education = re.search(r"学历要求：\s*(.*?)\s*招聘人数：", info_text)
    count = re.search(r"招聘人数：\s*(\d+)\s*人", info_text)
    check(
        all(item is not None for item in (location, category, education, count)),
        "天山铝业高校岗位地点、学历或人数改变",
    )
    assert location is not None and category is not None and education is not None
    assert count is not None
    body = sections[0].get_text("\n", strip=True)
    check(
        "岗位职责：" in body and "所需专业：" in body and "正式录用：签订劳动合同" in body,
        "天山铝业高校校招生正文改变",
    )
    duties = body.split("岗位职责：", 1)[1].split("所需专业：", 1)[0].strip()
    requirements = body.split("所需专业：", 1)[1].split("保障福利：", 1)[0].strip()
    check(bool(duties) and bool(requirements), "天山铝业高校岗位职责或专业要求缺失")
    return {
        "title": title,
        "location": location.group(1).strip(),
        "category": category.group(1).strip(),
        "education": education.group(1).strip(),
        "headcount": count.group(1),
        "published": published_match.group(1),
        "duties": duties,
        "requirements": requirements,
    }


class TianshanHebutCampus(Adapter):
    name = "tianshan-hebut-campus"
    host = "career.hebut.edu.cn"
    path = PROFILE_PATH
    scope_description = "天山铝业河北工业大学企业账户公开校招生目录；覆盖该账号当前全部岗位"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "天山铝业高校企业主页未就绪")
        rows = profile_jobs(await session.page.content())
        profile_evidence = self.session.last_evidence
        scope = Scope(name="tianshan-hebut-all-campus", expected=len(rows))
        scope.evidence.append(profile_evidence)
        self.result.scopes.append(scope)
        seen: set[str] = set()
        for row in self.add_page(scope, rows, seen, lambda item: item["id"]):
            key = row["id"]
            try:
                await self.session.open(row["url"])
                check(session.page is not None, "天山铝业高校岗位详情未就绪")
                data = detail_job(await session.page.content(), row)
                evidence = self.session.last_evidence
                job = self.job(
                    key,
                    title=data["title"],
                    work_type="校招",
                    source_url=row["url"],
                    unit=EMPLOYER,
                    location=data["location"],
                    education=data["education"],
                    category_raw=data["category"],
                    duties=data["duties"],
                    requirements=data["requirements"],
                    published=data["published"],
                    field_sources={
                        "unit": "详情 .info 企业账号 19244",
                        "location": "详情 .info 工作地域",
                        "education": "详情 .info 学历要求",
                        "category_raw": "详情 .info 职位类别",
                        "duties": "详情 .content 岗位职责",
                        "requirements": "详情 .content 所需专业",
                        "published": "详情 .info 发布时间",
                        "deadline": "source_missing:详情未给截止日期",
                        "headcount": f"详情 .info 招聘人数={data['headcount']}；不拆分岗位",
                    },
                )
                job.evidence = [profile_evidence, evidence]
                reused = self.before_detail(f"job:{key}", row, scope, job, evidence=evidence)
                if reused is not None:
                    self.result.jobs.extend(reused)
                    continue
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            except Exception as exc:
                self.error(exc, key)
        scope.terminal = True
