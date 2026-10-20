"""Fufeng subsidiary's current graduate jobs in a university employer account."""

import re
from typing import cast
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

ROOT = "https://jy.tust.edu.cn"
EMPLOYER = "内蒙古沃丰农业发展有限公司"
PROFILE_PATH = "/company/index/id/16813.html"
DETAIL_RE = re.compile(r"/correcruit/content/id/(\d+)\.html")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def profile_jobs(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    employer = soup.select_one(".company_index .p1")
    check(employer is not None and text(employer.get_text()) == EMPLOYER, "沃丰高校企业账号变化")
    check(not soup.select(".page a, .pagination a"), "沃丰高校企业目录出现分页")
    links = soup.select("a.lizw[href]")
    check(bool(links), "沃丰高校企业目录没有公开岗位")
    rows: list[dict[str, str]] = []
    for link in links:
        path = urlsplit(str(link.get("href") or "")).path
        match = DETAIL_RE.fullmatch(path)
        title = link.select_one(".zw_title .p1")
        published = link.select_one(".zw_title .p2")
        check(
            match is not None and title is not None and published is not None, "沃丰目录行结构变化"
        )
        assert match is not None and title is not None and published is not None
        date = text(published.get_text())
        check(DATE_RE.fullmatch(date) is not None, "沃丰目录发布日期缺失")
        name = text(title.get_text())
        check(bool(name), "沃丰目录岗位标题缺失")
        rows.append({"id": match[1], "title": name, "published": date, "url": urljoin(ROOT, path)})
    check(len({row["id"] for row in rows}) == len(rows), "沃丰目录重复岗位 ID")
    return rows


def detail_job(html: str, listed: dict[str, str]) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    panel = soup.select_one(".zhaopinxx_con1")
    check(panel is not None, "沃丰岗位详情缺失")
    assert panel is not None
    title = panel.select_one(".p1")
    employer = panel.select_one(f'a.p2[href="{PROFILE_PATH}"]')
    published = panel.select_one(".p3")
    check(
        title is not None and employer is not None and published is not None, "沃丰详情主体字段缺失"
    )
    assert title is not None and employer is not None and published is not None
    check(text(title.get_text()) == listed["title"], "沃丰目录与详情岗位标题错配")
    check(text(employer.get_text()) == EMPLOYER, "沃丰详情雇主错配")
    match = re.search(r"发布时间：\s*(\d{4}-\d{2}-\d{2})", published.get_text(" ", strip=True))
    check(match is not None and match[1] == listed["published"], "沃丰目录与详情日期错配")
    metadata: dict[str, str] = {}
    for item in panel.select(".zpxx_ul li"):
        part = text(item.get_text(" ", strip=True))
        if "：" in part:
            key, value = part.split("：", 1)
            metadata[key] = value.strip()
    check(
        all(metadata.get(key) for key in ("工作地域", "职位类别", "学历要求")), "沃丰岗位元数据缺失"
    )
    sections = {}
    for block in soup.select(".zhaopinxx_con2"):
        heading = block.select_one(".zhaopinxx_con2_title")
        content = block.select_one(".zhaopinxx_con2_con")
        if heading is not None and content is not None:
            sections[text(heading.get_text()).rstrip("：")] = text(
                content.get_text("\n", strip=True)
            )
    description = sections.get("职位描述", "")
    check(
        bool(sections.get("专业要求"))
        and "阜丰集团全资子公司" in description
        and "岗位职责:" in description
        and "岗位要求:" in description,
        "沃丰全资关系或岗位正文变化",
    )
    duties = description.split("岗位职责:", 1)[1].split("岗位要求:", 1)[0].strip()
    requirements = description.split("岗位要求:", 1)[1].split("福利待遇：", 1)[0].strip()
    check(bool(duties and requirements), "沃丰岗位职责或要求为空")
    return {
        "location": metadata["工作地域"],
        "category": metadata["职位类别"],
        "education": metadata["学历要求"],
        "majors": sections["专业要求"],
        "duties": duties,
        "requirements": requirements,
    }


class FufengTust2027(Adapter):
    name = "fufeng-tust-2027"
    host = "jy.tust.edu.cn"
    path = PROFILE_PATH
    scope_description = "天津科技大学沃丰农业高校账号当前 2027 届正式岗位"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(urlsplit(self.source.url).path == PROFILE_PATH, "沃丰来源入口不是已核验企业账号")
        check(session.page is not None, "沃丰高校企业账号未就绪")
        rows = profile_jobs(await session.page.content())
        profile_evidence = session.last_evidence
        scope = Scope(name="fufeng-tust-16813", expected=len(rows))
        scope.evidence.append(profile_evidence)
        self.result.scopes.append(scope)
        for row in self.add_page(scope, rows, set(), lambda item: item["id"]):
            if "2027届" not in row["title"]:
                scope.skipped_out_of_scope += 1
                continue
            try:
                await self.session.open(row["url"])
                check(session.page is not None, "沃丰岗位详情未就绪")
                data = detail_job(await session.page.content(), row)
                evidence = session.last_evidence
                job = self.job(
                    row["id"],
                    title=row["title"],
                    source_url=row["url"],
                    unit=EMPLOYER,
                    work_type="校招",
                    location=data["location"],
                    category_raw=data["category"],
                    education=data["education"],
                    duties=data["duties"],
                    requirements=f"{data['majors']}\n{data['requirements']}",
                    published=row["published"],
                    field_sources={
                        "unit": "高校企业账号与详情雇主；正文明确阜丰集团全资子公司",
                        "title": "目录与详情标题对应",
                        "location": "详情工作地域",
                        "category_raw": "详情职位类别",
                        "education": "详情学历要求",
                        "duties": "详情岗位职责段",
                        "requirements": "详情专业要求及岗位要求段",
                        "published": "目录与详情发布时间一致",
                        "deadline": "source_missing:高校详情未给截止日期",
                    },
                )
                job.evidence = [profile_evidence, evidence]
                reused = self.before_detail(f"job:{row['id']}", row, scope, job, evidence=evidence)
                if reused is not None:
                    self.result.jobs.extend(reused)
                    continue
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{row['id']}", row, [job])
            except Exception as exc:
                self.error(exc, row["id"])
        scope.terminal = True
