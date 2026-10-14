"""Bohai Bank's four public 2027 campus catalog pages."""

import json
from html import escape
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.campaign51 import apply_id
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

ROUTES = (
    ("总行管理培训生", "head.html"),
    ("总行培训见习生", "pxjx.html"),
    ("分行管理培训生", "branch1.html"),
    ("分行培训见习生", "branch2.html"),
)
ROOT = "https://campus.51job.com/bhyh2027/"
CTMID = "9570675"


class BohaiPage(Protocol):
    async def content(self) -> str: ...

    async def evaluate(self, script: str) -> Any: ...


class BohaiSession(Protocol):
    page: BohaiPage
    last_evidence: str

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None: ...

    def snapshot(self, label: str, html: str) -> str: ...


def _navigation(document: BeautifulSoup) -> None:
    links = {
        a.get_text(" ", strip=True): urljoin(ROOT, str(a.get("href", "")))
        for a in document.select(".navlist a[href]")
    }
    check(links.get("总行招聘") == ROOT + "head.html", "渤海银行总行导航变化")
    check(links.get("分行招聘") == ROOT + "branch1.html", "渤海银行分行导航变化")
    check(links.get("渤银理财招聘") == ROOT + "bylc.html", "渤银理财主体边界变化")


def _requirements(document: BeautifulSoup) -> tuple[str, str]:
    groups = document.select(".zpyq > .list")
    check(len(groups) == 2, "渤海银行招聘对象或招聘要求结构变化")
    audience = groups[0].get_text("\n", strip=True)
    conditions = groups[1].get_text("\n", strip=True)
    check("2027届" in audience and bool(conditions), "渤海银行招聘范围或要求缺失")
    education = "硕士" if "硕士研究生及以上" in audience else "本科"
    check(education == "硕士" or "大学本科及以上" in audience, "渤海银行学历范围变化")
    return audience + "\n" + conditions, education


def _detail_link(url: str) -> tuple[str, int]:
    parts = urlsplit(url)
    params = parse_qs(parts.query)
    check(
        parts.scheme == "https"
        and parts.hostname == "campus.51job.com"
        and parts.path == "/bhyh2027/detail.html"
        and len(params.get("id", [])) == len(params.get("jobid", [])) == 1
        and params["id"][0].isdigit()
        and params["jobid"][0].isdigit(),
        "渤海银行分行详情 ID 异常",
    )
    return params["jobid"][0], int(params["id"][0])


class Bohai2027(Adapter):
    name = "bohai-2027"
    host = "campus.51job.com"
    path = "/bhyh2027/head.html"
    scope_description = "渤海银行2027总行两类、分行两类公开岗位；排除渤银理财独立主体"

    async def harvest(self) -> None:
        session = cast(BohaiSession, self.session)
        seen: set[str] = set()
        branch_rows: list[tuple[Scope, str, int, str, str, str, str, str]] = []
        head = BeautifulSoup(await session.page.content(), "html.parser")
        _navigation(head)
        for label, route in ROUTES:
            scope = Scope(name=route.removesuffix(".html"))
            self.result.scopes.append(scope)
            try:
                url = ROOT + route
                if route != "head.html":
                    await session.open(url)
                html = await session.page.content()
                document = BeautifulSoup(html, "html.parser")
                _navigation(document)
                links = {
                    a.get_text(" ", strip=True): urljoin(ROOT, str(a.get("href", "")))
                    for a in document.select(".a-list a[href]")
                }
                check(links.get(label) == url, f"渤海银行{label}导航缺失")
                requirements, education = _requirements(document)
                evidence = session.snapshot("bohai-" + scope.name, html)
                scope.evidence.append(evidence)
                if route in {"head.html", "pxjx.html"}:
                    applies = document.select('.zpyq a.abtn[href*="external/apply.aspx"]')
                    check(len(applies) == 1, f"渤海银行{label}申请 ID 不唯一")
                    apply_url = urljoin(url, str(applies[0].get("href", "")))
                    check(
                        parse_qs(urlsplit(apply_url).query).get("ctmid") == [CTMID],
                        "渤海银行总行租户 ID 改变",
                    )
                    job_id = apply_id(apply_url)
                    scope.listed += 1
                    check(job_id not in seen, "渤海银行岗位 ID 重复")
                    seen.add(job_id)
                    scope.unique += 1
                    self.result.jobs.append(
                        self.job(
                            job_id,
                            title=label,
                            unit="总行",
                            location="",
                            education=education,
                            requirements=requirements,
                            source_url=url,
                            apply_url=apply_url,
                            field_sources={
                                "title": ".a-list 当前招聘类别",
                                "education": ".zpyq 招聘对象",
                                "location": "source_missing:总行页无工作地点",
                                "requirements": ".zpyq 招聘对象与招聘要求",
                                "duties": "source_missing:无岗位职责",
                                "published": "source_missing:无公开发布日期",
                                "deadline": "source_missing:无公开截止日",
                            },
                        )
                    )
                    self.result.jobs[-1].evidence = [evidence]
                    scope.details += 1
                else:
                    cards = document.select(".city-box a.item[href]")
                    check(bool(cards), f"渤海银行{label}城市目录为空")
                    for card in cards:
                        scope.listed += 1
                        detail_url = urljoin(url, str(card.get("href", "")))
                        job_id, index = _detail_link(detail_url)
                        check(job_id not in seen, "渤海银行跨范围岗位 ID 重复")
                        seen.add(job_id)
                        scope.unique += 1
                        city_node = card.select_one(".name")
                        check(city_node is not None, "渤海银行分行城市缺失")
                        assert city_node is not None
                        city = city_node.get_text(" ", strip=True)
                        check(bool(city), "渤海银行分行城市为空")
                        branch_rows.append(
                            (scope, job_id, index, city, label, requirements, education, detail_url)
                        )
                scope.expected = scope.listed
                if route in {"head.html", "pxjx.html"}:
                    scope.terminal = True
            except Exception as exc:
                self.error(exc, label)

        if not branch_rows:
            return
        try:
            # Every branch detail loads the same public bank-description array. One
            # detail page provides the complete array for all listed city IDs.
            await session.open(branch_rows[0][-1])
            detail_html = await session.page.content()
            detail_document = BeautifulSoup(detail_html, "html.parser")
            scripts = {str(node.get("src", "")) for node in detail_document.select("script[src]")}
            check(
                "./js/job.js" in scripts and "./js/detail.js" in scripts,
                "渤海银行分行详情数据脚本变化",
            )
            detail_evidence = session.snapshot("bohai-branch-detail", detail_html)
            rows = await session.page.evaluate("() => typeof lists === 'undefined' ? null : lists")
            check(isinstance(rows, list) and bool(rows), "渤海银行分行详情数组缺失")
            script_evidence = session.snapshot(
                "bohai-branch-units",
                "<html><body><pre>"
                + escape(json.dumps(rows, ensure_ascii=False))
                + "</pre></body></html>",
            )
            for (
                scope,
                job_id,
                index,
                city,
                label,
                requirements,
                education,
                detail_url,
            ) in branch_rows:
                check(0 < index <= len(rows), "渤海银行分行详情索引越界")
                row = rows[index - 1]
                check(
                    isinstance(row, dict)
                    and isinstance(row.get("area"), str)
                    and city.startswith(row["area"]),
                    "分行城市与详情不符",
                )
                bank = row.get("bank")
                check(isinstance(bank, list) and len(bank) == 1, "分行单位结构变化")
                unit = bank[0].get("name") if isinstance(bank[0], dict) else None
                check(isinstance(unit, str) and unit.startswith(city), "分行单位与城市不符")
                apply_url = (
                    f"https://xyz.51job.com/external/apply.aspx?jobid={job_id}&ctmid={CTMID}"
                )
                job = self.job(
                    job_id,
                    title=f"{label}（{city}）",
                    unit=unit,
                    location=city,
                    education=education,
                    requirements=requirements,
                    source_url=detail_url,
                    apply_url=apply_url,
                    field_sources={
                        "title": ".a-list 当前招聘类别 + .city-box .name",
                        "unit": "js/job.js lists[id-1].bank[0].name",
                        "location": ".city-box .name",
                        "education": ".zpyq 招聘对象",
                        "requirements": ".zpyq 招聘对象与招聘要求",
                        "duties": "source_missing:无岗位职责",
                        "published": "source_missing:无公开发布日期",
                        "deadline": "source_missing:无公开截止日",
                    },
                )
                job.evidence.extend([script_evidence, detail_evidence])
                self.result.jobs.append(job)
                scope.details += 1
            for scope in self.result.scopes:
                if scope.name in {"branch1", "branch2"}:
                    scope.evidence.extend([script_evidence, detail_evidence])
                    scope.terminal = True
        except Exception as exc:
            self.error(exc, "branch-detail-data")
