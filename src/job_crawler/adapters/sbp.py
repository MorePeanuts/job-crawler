"""Sino Biopharm's five explicitly linked member campus catalogs."""

import re
from typing import Any, cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.adapters.zhiye import Zhiye
from job_crawler.description import split_sections
from job_crawler.models import Job, Scope
from job_crawler.transport import BrowserSession


class Branch(Adapter):
    prefix = ""
    member = ""

    def job(self, key: str, **fields: Any) -> Job:
        fields["unit"] = fields.get("unit") or self.member
        return super().job(f"{self.prefix}:{key}", **fields)

    def entity_key(self, entity: str) -> str:
        kind, separator, key = entity.partition(":")
        check(kind == "job" and bool(separator), "中生分支增量对象类型变化")
        return f"job:{self.prefix}:{key}"

    def before_detail(
        self,
        entity: str,
        listing: object,
        scope: Scope,
        listing_job: Job | None = None,
        *,
        evidence: str | None = None,
    ) -> list[Job] | None:
        return super().before_detail(
            self.entity_key(entity), listing, scope, listing_job, evidence=evidence
        )

    def remember(self, entity: str, listing: object, jobs: list[Job]) -> None:
        super().remember(self.entity_key(entity), listing, jobs)


class Cttq(Branch, Zhiye):
    prefix = "cttq"
    member = "正大天晴药业集团股份有限公司"
    host = "cttq.zhiye.com"
    listing_complete = True
    regular_only = True


class Njcttq(Cttq):
    prefix = "njcttq"
    member = "南京正大天晴制药有限公司"
    host = "njcttq.zhiye.com"


class Zdfh(Cttq):
    prefix = "zdfh"
    member = "江苏正大丰海制药有限公司"
    host = "zdfh.zhiye.com"


def tide_details(html: str, title: str, key: str) -> dict[str, str]:
    doc = BeautifulSoup(html, "html.parser")
    heading = doc.select_one(".xiangqingtitle > span")
    check(heading is not None, "泰德详情标题缺失")
    assert heading is not None
    for status in heading.select(".applyStatus"):
        status.decompose()
    identity = re.search(r"var jobAdId\s*=\s*(\d+)", html)
    check(
        heading.get_text(strip=True) == title and identity is not None and identity[1] == key,
        "泰德详情身份错配",
    )
    values = {
        n.get_text(strip=True).rstrip("：:"): text(n.find_next_sibling("li"))
        for n in doc.select("li.ntitle")
    }
    check(values.get("招聘类别") == "校园招聘", "泰德详情不是校园招聘")
    body = doc.select_one(".xiangqingtext")
    check(body is not None and not body.select("a,img,iframe"), "泰德正文缺失或出现附件")
    assert body is not None
    paragraphs = body.find_all("p", recursive=False)
    check(
        len(paragraphs) == 6
        and [text(n) for n in paragraphs[::2]] == ["工作地点：", "工作职责：", "任职资格："],
        "泰德正文结构变化",
    )
    location, duties, requirements = [text(n) for n in paragraphs[1::2]]
    check(bool(location and duties and requirements), "泰德正文为空")
    return {
        "location": location,
        "duties": duties,
        "requirements": requirements,
        "published": values.get("发布时间", ""),
        "deadline": values.get("截止时间", ""),
        "work_type": "实习" if "实习" in values.get("工作性质", "") else "校招",
    }


class Tide(Branch):
    prefix = "tide"
    member = "北京泰德制药股份有限公司"
    host = "tidepharm.zhiye.com"
    path = "/Campus"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        scope = Scope(name="tide-campus")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        visited: set[str] = set()
        target = f"https://{self.host}{self.path}"
        html = await session.page.content()
        while True:
            check(target not in visited, "泰德分页循环")
            visited.add(target)
            doc = BeautifulSoup(html, "html.parser")
            check(
                self.member in doc.get_text() and "校招分类" in doc.get_text(), "泰德校园身份变化"
            )
            count = re.fullmatch(r"共\s*(\d+)\s*条记录", text(doc.select_one(".tablenote")))
            check(count is not None, "泰德目录总数缺失")
            assert count is not None
            if scope.expected is None:
                scope.expected = int(count[1])
            check(scope.expected == int(count[1]), "泰德目录总数变化")
            scope.evidence.append(session.last_evidence)
            evidence = session.last_evidence
            cards = doc.select(".listtable tbody tr")
            check(bool(cards) or scope.expected == 0, "泰德目录提前为空")
            for card in cards:
                cells = card.find_all("td", recursive=False)
                anchor = card.select_one('a[href^="/zpdetail/"][jobadid]')
                check(len(cells) == 4 and anchor is not None, "泰德列表结构改变")
                assert anchor is not None
                key, title = str(anchor["jobadid"]), anchor.get_text(strip=True)
                check(
                    key.isdigit() and str(anchor["href"]) == f"/zpdetail/{key}" and key not in seen,
                    "泰德重复或错误岗位ID",
                )
                seen.add(key)
                scope.listed += 1
                scope.unique += 1
                if "实习" in title:
                    scope.skipped_out_of_scope += 1
                    continue
                listing = str(card)
                cached = self.before_detail(f"job:{key}", listing, scope, evidence=evidence)
                if cached is not None:
                    self.result.jobs.extend(cached)
                    continue
                try:
                    url = f"https://{self.host}/zpdetail/{key}"
                    detail = await session.request_html(url, detail=True)
                    fields = tide_details(detail, title, key)
                    job = self.job(
                        key,
                        title=title,
                        source_url=url,
                        category_raw=text(cells[1]),
                        **fields,
                        field_sources={
                            "published": "详情发布时间",
                            "deadline": "详情截止时间，空值不推断",
                        },
                    )
                    job.evidence = [evidence, session.last_evidence]
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{key}", listing, [job])
                except Exception as exc:
                    self.error(exc, key)
            pages = [urljoin(target, str(a["href"])) for a in doc.select('a[href*="PageIndex="]')]
            check(
                all(
                    urlsplit(u).hostname == self.host
                    and urlsplit(u).path.lower().rstrip("/") == "/campus"
                    for u in pages
                ),
                "泰德分页路径变化",
            )
            if scope.unique == scope.expected:
                scope.terminal = True
                break
            check(scope.unique < scope.expected, "泰德目录数量超出总数")
            pending = [u for u in pages if u not in visited]
            check(bool(pending), "泰德缺少后续分页，不能声称完整")
            target = pending[0]
            html = await session.request_html(target)


def qingjiang_fields(body: str) -> tuple[str, str, str, bool]:
    body = body.removeprefix("招聘条件").strip()
    if "从事药品研发分析工作1年以上" in body and "应届" not in body:
        return "", body, "", False
    if "任职" in body:
        duties, requirements = split_sections(body, unheaded_duties=False)
    else:
        duties, requirements = "", body
    check(bool(requirements), "清江任职要求缺失")
    education = "硕士" if "应届硕士或本科一年以上工作经验者" in requirements else ""
    return duties, requirements, education, True


class Qingjiang(Branch):
    prefix = "qingjiang"
    member = "江苏正大清江制药有限公司"
    host = "www.ctqjph.com"
    path = "/human_xy.aspx"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        doc = BeautifulSoup(await session.page.content(), "html.parser")
        check(
            self.member in doc.get_text() and doc.select_one('a[href="human_xy.aspx"]') is not None,
            "清江校园身份变化",
        )
        check(not doc.select(".pagination,.pager,[class*=paging]"), "清江出现未知分页")
        cards = doc.select("#bs-collapse > .panel")
        check(bool(cards), "清江校园目录缺失")
        scope = Scope(
            name="qingjiang-campus", expected=len(cards), evidence=[session.last_evidence]
        )
        self.result.scopes.append(scope)
        seen: set[str] = set()
        for card in cards:
            scope.listed += 1
            try:
                values = [text(n) for n in card.select(".panel-title > a > span")]
                link = card.select_one("a.join[href]")
                blocks = card.select(".zp_nei")
                check(
                    len(values) == 5 and link is not None and len(blocks) == 2, "清江岗位结构改变"
                )
                assert link is not None
                url = urlsplit(str(link["href"]))
                ids = parse_qs(url.query).get("id", [])
                check(
                    url.path == "human_zp_n.aspx" and len(ids) == 1 and ids[0].isdigit(),
                    "清江岗位ID变化",
                )
                key = ids[0]
                check(key not in seen, "清江岗位ID重复")
                seen.add(key)
                scope.unique += 1
                check(
                    text(blocks[0].select_one("h2")) == "招聘条件"
                    and text(blocks[1].select_one("h2")) == "联系方式",
                    "清江正文分段变化",
                )
                check(not blocks[0].select("img,a,iframe"), "清江出现未处理岗位附件")
                duties, requirements, education, eligible = qingjiang_fields(text(blocks[0]))
                if "实习" in values[1] or not eligible:
                    scope.skipped_out_of_scope += 1
                    continue
                listing = str(card)
                cached = self.before_detail(f"job:{key}", listing, scope)
                if cached is not None:
                    self.result.jobs.extend(cached)
                    continue
                job = self.job(
                    key,
                    title=values[1],
                    category_raw=values[0],
                    location=values[3],
                    duties=duties,
                    requirements=requirements,
                    education=education,
                    source_url=f"https://{self.host}{self.path}",
                    field_sources={
                        "requirements": "校园卡片完整招聘条件",
                        "education": "应届硕士条件"
                        if education
                        else "source_missing:待公共学历补全",
                        "published": "source_missing",
                        "deadline": "source_missing",
                    },
                )
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", listing, [job])
            except Exception as exc:
                self.error(exc)
        scope.terminal = True


LINKS = {
    "正大天晴": "https://cttq.zhiye.com/",
    "北京泰德": "http://www.tidepharm.com/zpxx_0915",
    "南京正大天晴": "https://njcttq.zhiye.com/",
    "正大丰海": "https://zdfh.zhiye.com/",
    "正大清江": "https://www.ctqjph.com/human_zp.aspx",
}
BRANCHES = (Cttq, Njcttq, Zdfh, Tide, Qingjiang)


def validate_members(html: str) -> None:
    doc = BeautifulSoup(html, "html.parser")
    check("中国生物制药" in doc.get_text(), "中生集团主体变化")
    first = doc.select_one('a[title="正大天晴"]')
    listing = first.find_parent("ul") if first is not None else None
    check(isinstance(listing, Tag), "中生成员招聘导航缺失")
    assert isinstance(listing, Tag)
    links = {str(a.get("title")): str(a.get("href")) for a in listing.select("a[href]")}
    check(links == LINKS, "中生成员招聘导航变化")


class SbpCampus(Adapter):
    name = "sbp-group-campus"
    host = "www.sbpgroup.com"
    path = "/career-development/"
    scope_description = (
        "中国生物制药官网五成员全部校园目录；排除实习和明确需工作经验且无应届替代的岗位"
    )

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        validate_members(await session.page.content())
        navigation_evidence = session.last_evidence
        original_output = session.output
        for branch in BRANCHES:
            try:
                session.output = original_output / branch.prefix
                session.output.mkdir(parents=True, exist_ok=True)
                member_evidence = [navigation_evidence]
                if branch is Tide:
                    await session.open("https://www.tidepharm.com/zpxx_0915")
                    doc = BeautifulSoup(await session.page.content(), "html.parser")
                    check(
                        doc.select_one('a[href="https://tidepharm.zhiye.com/"]') is not None
                        and Tide.member in doc.get_text(),
                        "泰德官网招聘门户关联变化",
                    )
                    member_evidence.append(session.last_evidence)
                source = self.source.model_copy(
                    update={"url": f"https://{branch.host}{branch.path}"}
                )
                result = await branch(
                    source, session, self.collected_at, self.as_of, incremental=self.incremental
                ).collect()
                for scope in result.scopes:
                    scope.name = f"{branch.prefix}:{scope.name}"
                    scope.evidence.extend(member_evidence)
                self.result.scopes.extend(result.scopes)
                self.result.jobs.extend(result.jobs)
                self.result.issues.extend(result.issues)
                self.result.warnings.extend(result.warnings)
            except Exception as exc:
                self.error(exc, branch.prefix)
            finally:
                session.output = original_output
