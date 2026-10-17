"""TFME's complete employer catalog on Hubei's public graduate jobs portal."""

import re
from typing import cast
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.description import split_sections
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession, CrawlError

COMPANY = "通富微电子股份有限公司"
ROOT = "https://www.91wllm.cn"
EMPLOYER = ROOT + "/companydetail/view/id/410286"


def catalog(html: str) -> tuple[int, list[dict[str, str]]]:
    document = BeautifulSoup(html, "html.parser")
    names = [n.get_text(strip=True) for n in document.select(".unit-info .title h5")]
    check(names == [COMPANY], "通富企业目录主体改变")
    counts = document.select("[v-text-job-total]")
    check(len(counts) == 1, "通富在招总数缺失或重复")
    match = re.fullmatch(r"(\d+)个", counts[0].get_text(strip=True))
    check(match is not None, "通富在招总数尚未加载")
    assert match is not None
    expected = int(match[1])
    check(not document.select(".pagination,.pager"), "通富目录新增分页，需扩展遍历")
    rows: list[dict[str, str]] = []
    for anchor in document.select('table a[href*="/job/view/id/"]'):
        url = str(anchor.get("href", ""))
        identity = re.fullmatch(re.escape(ROOT) + r"/job/view/id/(\d+)", url)
        check(identity is not None, "通富岗位链接结构改变")
        assert identity is not None
        row = anchor.find_parent("tr")
        check(row is not None, "通富职位表格行缺失")
        assert row is not None
        controls = row.select("a.apply_job[data-id]")
        check(
            len(controls) == 1 and str(controls[0].get("data-id")) == identity[1],
            "通富目录详情和投递ID不一致",
        )
        title = anchor.get_text(strip=True)
        check(title.endswith("-27") and "实习" not in title, "通富出现未经验证的招聘届别或类型")
        rows.append({"id": identity[1], "title": title, "url": url})
    check(len(rows) == expected, "通富总数与已显示职位数不一致")
    check(len({r["id"] for r in rows}) == len(rows), "通富目录出现重复岗位ID")
    return expected, rows


def detail(html: str, listed: dict[str, str]) -> dict[str, str]:
    document = BeautifulSoup(html, "html.parser")
    titles = [n.get_text(strip=True) for n in document.select(".title-message .title")]
    check(titles == [listed["title"]], "通富详情标题与列表不一致")
    employers = document.select('.title-message a[href*="/companydetail/view/id/"]')
    check(
        len(employers) == 1
        and employers[0].get_text(strip=True) == COMPANY
        and employers[0].get("href") == EMPLOYER,
        "通富详情雇主身份改变",
    )
    shares = document.select(".share-link a.icon-qq[href]")
    check(len(shares) == 1, "通富详情缺少公开页面身份")
    urls = parse_qs(urlsplit(str(shares[0]["href"])).query).get("url", [])
    check(len(urls) == 1, "通富详情页面身份不唯一")
    path = urlsplit(urls[0])
    check(
        path.hostname == "www.91wllm.cn"
        and re.fullmatch(r"/job/view/id/" + re.escape(listed["id"]), path.path) is not None,
        "通富详情岗位ID错配",
    )
    sections = []
    for node in document.select(".details-mge"):
        heading = node.select_one(".mge-title")
        if heading is not None and heading.get_text(strip=True) == "职位详情":
            sections.append(node)
    check(len(sections) == 1, "通富职位详情章节缺失或重复")
    bodies = sections[0].select(".aContent")
    check(len(bodies) == 1, "通富职位正文结构改变")
    body = bodies[0]
    check(not body.select("a[href],img,iframe,object,embed"), "通富职位正文含未处理附件或链接")
    duties, requirements = split_sections(body.get_text("\n", strip=True))
    check(bool(duties and requirements), "通富职位正文缺少职责或任职要求")
    majors = []
    for item in document.select("li.full-width"):
        value = item.get_text("", strip=True)
        if value.startswith("需求专业："):
            majors.append(value)
    check(len(majors) == 1, "通富详情需求专业缺失或重复")
    degrees = re.findall(
        r"^\s*(?:\d+[、.．]\s*)?(?:全日制)?(博士|硕士|本科)(?:学历|及以上)",
        requirements,
        re.MULTILINE,
    )
    education = degrees[0] if len(degrees) == 1 else ""
    return {
        "duties": duties,
        "requirements": requirements + "\n" + majors[0],
        "education": education,
    }


class TfmeCampus(Adapter):
    name = "tfme-hubei-campus"
    host = "www.91wllm.cn"
    path = "/companydetail/view/id/410286/tab/1"
    ready_endpoints = ("/companydetail/statInfo/id/410286",)
    scope_description = "通富微电在湖北官方就业平台的完整企业在招目录；已与2027高校招聘会核对，不含其他子公司独立渠道"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        expected, rows = catalog(await session.page.content())
        scope = Scope(name="tfme-hubei-company-410286", expected=expected)
        self.result.scopes.append(scope)
        list_evidence = session.last_evidence
        for row in self.add_page(scope, rows, set(), lambda r: r["id"]):
            try:
                listing = self.job(row["id"], title=row["title"], source_url=row["url"])
                listing.evidence = [list_evidence]
                reused = self.before_detail(
                    f"job:{row['id']}", row, scope, listing, evidence=list_evidence
                )
                if reused is not None:
                    self.result.jobs.extend(reused)
                    continue
                values = detail(await session.request_html(row["url"], detail=True), row)
                job = self.job(
                    row["id"],
                    title=row["title"],
                    source_url=row["url"],
                    unit=COMPANY,
                    work_type="校招",
                    **values,
                    field_sources={
                        "duties": "湖北官方就业平台.职位详情.明确职责章节",
                        "requirements": "职位详情.明确任职章节及需求专业",
                        "education": "正文明确任职学历优先于摘要不限；无明确要求留空",
                        "location": "source_missing:岗位未给工作地点，企业地址不代填",
                        "address": "source_missing:岗位未给详细地址",
                        "published": "source_missing:未披露职位发布时间，宣讲和企业登录时间不代填",
                        "deadline": "source_missing:未披露报名截止时间",
                    },
                )
                job.evidence = [list_evidence, session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{row['id']}", row, [job])
            except Exception as exc:
                self.error(exc, row["id"])
                if isinstance(exc, CrawlError) and exc.code in {
                    "access_denied",
                    "request_budget",
                    "time_budget",
                }:
                    return
        scope.terminal = True
