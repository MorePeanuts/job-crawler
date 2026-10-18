"""New World's unified public vacancies and non-employment youth programmes."""

import hashlib
import re
from dataclasses import dataclass
from typing import cast
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession, CrawlError

ENTRY = "https://www.nwd.com.hk/zh-hans/people/job-opportunities"
PROGRAMME = "https://nwd.com.hk/people/trainee-programme"
JOB_URL = re.compile(r"https://careers\.nwplatform\.com/job-invite/(\d+)")
PROGRAMME_HASH = "d9bc86e4ec5f555451229d69be1d6171f9bb2e355620c4b482d0c76c34cefffd"


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class Vacancy:
    key: str
    title: str
    url: str
    uploaded: str


def catalog(html: str) -> list[Vacancy]:
    doc = BeautifulSoup(html, "html.parser")
    check("新世界发展有限公司" in doc.get_text(), "新世界目录主体变化")
    views = doc.select(".view-current-vacancies")
    check(len(views) == 1, "新世界统一目录缺失或不唯一")
    view = views[0]
    check(
        not doc.select('[class*="pager"], [class*="pagination"], .load-more')
        and not re.search(r"加载更多|下一页|load more|next page", view.get_text(), re.I),
        "新世界目录出现未经核验的分页",
    )
    tables = view.select("table")
    check(len(tables) == 1, "新世界统一职位表缺失或变更")
    rows: list[Vacancy] = []
    for tr in tables[0].select("tbody tr"):
        links = tr.select("a[href]")
        check(len(links) == 1, "新世界职位行链接数量变化")
        url = str(links[0]["href"])
        match = JOB_URL.fullmatch(url)
        check(match is not None, "新世界岗位链接未知或非公开详情")
        assert match is not None
        title = clean(links[0].get_text())
        stamp = tr.select_one(".date-display-single")
        check(bool(title) and stamp is not None, "新世界职位标题或上载日期缺失")
        assert stamp is not None
        uploaded = clean(stamp.get_text())
        check(
            re.fullmatch(r"20\d{2}年\d{1,2}月\d{1,2}日", uploaded) is not None,
            "新世界上载日期结构变化",
        )
        rows.append(Vacancy(match[1], title, url, uploaded))
    check(1 <= len(rows) <= 1000, "新世界职位表为空或超过范围上限")
    check(len({r.key for r in rows}) == len(rows), "新世界岗位ID重复")
    all_links = [str(a["href"]) for a in doc.select('a[href*="/job-invite/"]')]
    check(all_links == [r.url for r in rows], "新世界目录表之外存在未遍历职位")
    check("其他公司的职位" in doc.get_text(), "新世界统一目录末端说明变化")
    return rows


def experience(html: str, row: Vacancy) -> str:
    doc = BeautifulSoup(html, "html.parser")
    title = doc.select_one("h1 [itemprop=title]")
    check(title is not None and clean(title.get_text()) == row.title, "新世界详情标题错配")
    identities = re.findall(r'"internalId"\s*:\s*"([^"\\]+)"', html)
    check(identities == [row.key + "-en_US"], "新世界公开详情身份错配")
    bodies = doc.select(".jobdescription")
    check(len(bodies) == 1, "新世界岗位正文缺失或不唯一")
    body = bodies[0].get_text("\n", strip=True)
    if re.search(
        r"(?:fresh|recent|new)\s+graduates?|entry[- ]level|graduate\s+trainee|"
        r"no\s+(?:prior\s+|working\s+)?experience|应届|應屆|无需经验|無需經驗",
        row.title + "\n" + body,
        re.I,
    ):
        raise CrawlError("unsupported_scope", "新世界出现应届或无经验岗位，须先核验校招字段及状态")
    headers = list(re.finditer(r"^\s*Requirements\s*:?\s*$", body, re.I | re.M))
    check(len(headers) == 1, "新世界任职要求标题缺失或不唯一")
    requirements = body[headers[0].end() :]
    for line in re.split(r"[\n•]", requirements):
        line = clean(line)
        match = re.search(
            r"\b(\d+)(?:\s*[-–]\s*\d+)?\s*[-+]?\s*years?\b.{0,120}\bexperiences?\b", line, re.I
        )
        if match is None or int(match[1]) == 0:
            continue
        if re.search(
            r"(?:would be|is|are)\s+(?:an?\s+)?(?:advantage|preferred|a plus)|preferred\s*\d",
            line,
            re.I,
        ):
            continue
        return line
    raise CrawlError("unsupported_scope", "新世界岗位没有明确必需的工作经验条件，不能按非校招排除")


def programme(html: str) -> str:
    doc = BeautifulSoup(html, "html.parser")
    title = doc.select_one(".pageTitle")
    check(
        title is not None and clean(title.get_text()) == "Nurturing the Leaders of Tomorrow",
        "新世界青年栏目标题缺失",
    )
    bodies = doc.select(".field-name-body")
    check(len(bodies) == 1, "新世界青年栏目正文缺失或不唯一")
    body = bodies[0]
    semantic = (
        clean(body.get_text(" ", strip=True))
        + "\n"
        + "\n".join(
            urljoin(PROGRAMME, str(node[attr]))
            for node in body.select("a[href],img[src]")
            for attr in ("href" if node.name == "a" else "src",)
        )
    )
    check(
        hashlib.sha256(semantic.encode()).hexdigest() == PROGRAMME_HASH,
        "新世界青年栏目内容变化，不能沿用实习/非招聘结论",
    )
    return "HYAB暑假实习；共创明Teen青年培育，非正式校园岗位"


class NewWorldCareers(Adapter):
    name = "newworld-careers"
    host = "www.nwd.com.hk"
    path = "/zh-hans/people/job-opportunities"
    scope_description = (
        "新世界发展官网统一公开职位表及青年栏目；不包含仅列招聘邮箱的附属公司独立系统"
    )

    async def harvest(self) -> None:
        check(self.source.url == ENTRY, "新世界来源须为已验证完整统一职位表")
        browser = cast(BrowserSession, self.session)
        rows = catalog(await browser.page.content())
        scope = Scope(
            name="newworld-unified-vacancies",
            expected=len(rows),
            listed=len(rows),
            unique=len(rows),
            evidence=[browser.last_evidence],
        )
        self.result.scopes.append(scope)
        records: list[dict[str, str]] = []
        first_opened = False
        for row in rows:
            record = {
                "id": row.key,
                "title": row.title,
                "url": row.url,
                "uploaded_raw": row.uploaded,
            }
            records.append(record)
            try:
                if not first_opened:
                    await browser.open(row.url)
                    html = await browser.page.content()
                    first_opened = True
                else:
                    html = await browser.request_html(row.url)
                scope.evidence.append(browser.last_evidence)
                record["experience_evidence"] = experience(html, row)
                record["disposition"] = "明确需要工作经验，非当前正式校园岗位"
                scope.skipped_out_of_scope += 1
            except Exception as exc:
                record["disposition"] = "待核验"
                self.error(exc, row.key)
        scope.terminal = True
        path = browser.output / "newworld-vacancy-dispositions.json"
        write_json(path, records)
        scope.evidence.append(str(path))
        youth = Scope(name="newworld-youth-programmes", expected=1, listed=1, unique=1, unit="栏目")
        self.result.scopes.append(youth)
        try:
            await browser.open(PROGRAMME)
            check(browser.page.url.rstrip("/") == PROGRAMME, "新世界青年栏目跳转")
            reason = programme(await browser.page.content())
            youth.evidence.append(browser.last_evidence)
            path = browser.output / "newworld-youth-disposition.json"
            write_json(path, {"url": PROGRAMME, "disposition": reason})
            youth.evidence.append(str(path))
            youth.skipped_out_of_scope = 1
            youth.terminal = True
        except Exception as exc:
            self.error(exc)
