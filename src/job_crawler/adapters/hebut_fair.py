"""Current jobs of verified employers at HEBUT's 2027 graduate fair."""

import re
from dataclasses import dataclass
from typing import cast
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Collection, Scope
from job_crawler.transport import BrowserSession, CrawlError

ROOT = "https://career.hebut.edu.cn"
FAIR_PATH = "/recruitment/content/type/1/id/120.html"
FAIR_TITLE = "2027届毕业生秋季双选会"
DETAIL_RE = re.compile(r"/correcruit/content/id/(\d+)\.html")
PUBLISHED_RE = re.compile(r"发布时间：\s*(\d{4}-\d{2}-\d{2})")
SOCIAL_RE = re.compile(r"(?:\d+\s*年(?:及以上|以上)?(?:相关)?工作经验|社招|社会招聘)")


@dataclass(frozen=True)
class Tenant:
    company_id: str
    employer: str
    profile_id: str
    relation: str


TENANTS = {
    "COM0017": Tenant(
        "COM0017", "中信戴卡股份有限公司", "1292", "中国中信集团公司于1988年投资组建"
    ),
    "COM0019": Tenant("COM0019", "华润江中药业股份有限公司", "19524", "现为华润集团直管业务单元"),
    "COM0061": Tenant(
        "COM0061",
        "中国太平洋财产保险股份有限公司天津分公司",
        "4336",
        "中国太平洋保险（集团）股份有限公司",
    ),
    "COM0074": Tenant("COM0074", "江苏敬业钢铁有限责任公司", "19621", "隶属于敬业集团"),
    "COM0143": Tenant("COM0143", "中国化学工程第四建设有限公司", "18472", "中国化学工程集团公司"),
    "COM0237": Tenant("COM0237", "山东创新精密科技有限公司", "15401", "股票代码：600361"),
    "COM0397": Tenant(
        "COM0397",
        "芜湖新兴铸管有限责任公司",
        "7106",
        "芜湖新兴铸管有限责任公司为新兴铸管股份有限公司",
    ),
    "COM0414": Tenant(
        "COM0414",
        "天津铁路信号有限责任公司",
        "2223",
        "隶属于通号（西安）轨道交通工业集团有限公司",
    ),
    "COM0431": Tenant("COM0431", "河北立中集团", "10136", "立中四通轻合金集团股份有限公司"),
}


def profile_jobs(html: str, tenant: Tenant) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    name = soup.select_one(".company_index > .p1")
    intro = soup.select_one(".company_index_info")
    check(
        name is not None
        and text(name.get_text()) == tenant.employer
        and intro is not None
        and tenant.relation in intro.get_text(" ", strip=True),
        "高校企业账号或集团关系变化",
    )
    fair = soup.select_one(f'.company_index_info_zph a[href="{FAIR_PATH}"]')
    check(
        fair is not None and FAIR_TITLE in fair.get_text(" ", strip=True),
        "企业账号未关联 2027 届双选会",
    )
    links = soup.select(".lizw[href]")
    check(bool(links), "高校企业账号没有当前岗位")
    check(
        not any("下一页" in a.get_text(" ", strip=True) for a in soup.select("a")),
        "高校企业目录出现未支持的分页",
    )
    rows: list[dict[str, str]] = []
    for link in links:
        path = urlsplit(str(link.get("href") or "")).path
        match = DETAIL_RE.fullmatch(path)
        title = link.select_one(".zw_title .p1")
        published = link.select_one(".zw_title .p2")
        check(
            match is not None and title is not None and published is not None, "高校目录行结构变化"
        )
        assert match is not None and title is not None and published is not None
        date = text(published.get_text())
        check(re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) is not None, "高校目录日期缺失")
        if date < "2026-09-01":
            continue
        title_text = text(title.get_text())
        check(bool(title_text), "高校目录岗位名为空")
        rows.append(
            {
                "id": match[1],
                "title": title_text,
                "published": date,
                "url": urljoin(ROOT, path),
            }
        )
    check(bool(rows), "2027 届双选会关联账号没有当期岗位")
    check(len({row["id"] for row in rows}) == len(rows), "高校目录重复岗位 ID")
    return rows


def detail_job(html: str, listed: dict[str, str], tenant: Tenant) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    panel = soup.select_one(".zpxq")
    check(panel is not None, "高校岗位详情缺失")
    assert panel is not None
    title = panel.select_one(".title")
    employer = panel.select_one(f'.info a[href="/company/index/id/{tenant.profile_id}.html"]')
    published = panel.select_one(".info .fb")
    info = panel.select_one(".info")
    contents = panel.select(".content")
    check(
        all(item is not None for item in (title, employer, published, info)) and len(contents) >= 2,
        "高校岗位详情主体或字段缺失",
    )
    assert title is not None and employer is not None and published is not None and info is not None
    check(text(employer.get_text()) == f"【{tenant.employer}】", "高校岗位详情主体错配")
    salary = title.select_one(".gongzi")
    if salary is not None:
        salary.decompose()
    check(text(title.get_text()) == listed["title"], "高校目录与详情标题错配")
    date = PUBLISHED_RE.search(published.get_text(" ", strip=True))
    check(date is not None and date[1] == listed["published"], "高校目录与详情发布日期错配")
    info_text = info.get_text(" ", strip=True)
    location = re.search(r"工作地域：\s*(.*?)\s*职位类别：", info_text)
    category = re.search(r"职位类别：\s*(.*?)\s*学历要求：", info_text)
    education = re.search(r"学历要求：\s*(.*?)\s*招聘人数：", info_text)
    check(all(item is not None for item in (location, category, education)), "高校岗位元数据变化")
    assert location is not None and category is not None and education is not None
    majors = text(contents[0].get_text(" ", strip=True))
    duties = text(contents[1].get_text(" ", strip=True))
    check(bool(majors) and bool(duties), "高校岗位专业或正文为空")
    check(SOCIAL_RE.search(duties) is None, "岗位详情出现社招工作年限要求")
    job_title = listed["title"]
    if tenant.company_id == "COM0414" and job_title == tenant.employer:
        check(duties == "从事产品技术研发工作", "天津信号企业名标题无法确认具体岗位")
        job_title = "产品技术研发"
    return {
        "title": job_title,
        "published": listed["published"],
        "location": location[1].strip(),
        "category": category[1].strip(),
        "education": education[1].strip(),
        "majors": majors,
        "duties": duties,
    }


class HebutFair2027(Adapter):
    name = "hebut-fair-2027"
    host = "career.hebut.edu.cn"
    scope_description = "河北工业大学 2027 届双选会企业账号当期公开岗位，逐岗核对主体和详情"

    async def collect(self) -> Collection:
        try:
            tenant = TENANTS.get(self.source.company_id)
            check(tenant is not None, "未配置的河北工大 2027 双选会企业")
            assert tenant is not None
            parts = urlsplit(self.source.url)
            if parts.hostname != self.host:
                raise CrawlError("entry_mismatch", "高校来源 URL 与绑定平台不匹配")
            check(
                parts.path == f"/company/index/id/{tenant.profile_id}.html",
                "高校企业主页与租户配置不符",
            )
            await self.session.open(self.source.url)
            await self.harvest()
        except Exception as exc:
            self.error(exc)
        return self.result

    async def harvest(self) -> None:
        tenant = TENANTS.get(self.source.company_id)
        check(tenant is not None, "未配置的河北工大 2027 双选会企业")
        assert tenant is not None
        check(
            urlsplit(self.source.url).path == f"/company/index/id/{tenant.profile_id}.html",
            "高校企业主页与租户配置不符",
        )
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "高校企业主页未就绪")
        rows = profile_jobs(await session.page.content(), tenant)
        profile_evidence = session.last_evidence
        scope = Scope(name=f"hebut-2027-{tenant.profile_id}", expected=len(rows))
        scope.evidence.append(profile_evidence)
        self.result.scopes.append(scope)
        for row in self.add_page(scope, rows, set(), lambda item: item["id"]):
            key = row["id"]
            try:
                await self.session.open(row["url"])
                check(session.page is not None, "高校岗位详情未就绪")
                data = detail_job(await session.page.content(), row, tenant)
                evidence = session.last_evidence
                job = self.job(
                    key,
                    title=data["title"],
                    source_url=row["url"],
                    unit=tenant.employer,
                    work_type="校招",
                    location=data["location"],
                    education=data["education"],
                    category_raw=data["category"],
                    duties=data["duties"],
                    requirements=data["majors"],
                    published=data["published"],
                    field_sources={
                        "unit": f"高校企业账号 {tenant.profile_id}；简介：{tenant.relation}",
                        "title": "高校招聘简章目录与详情标题一致",
                        "location": "详情 .info 工作地域",
                        "education": "详情 .info 学历要求",
                        "category_raw": "详情 .info 职位类别",
                        "duties": "详情 .content 职位描述",
                        "requirements": "详情 .content 专业要求",
                        "published": "目录与详情发布时间一致",
                        "deadline": "source_missing:高校详情未给截止日期",
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
