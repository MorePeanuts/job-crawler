"""Three independently verified 51job campaign formats."""

import re
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Issue, Scope


class Page(Protocol):
    async def evaluate(self, script: str) -> Any: ...

    async def content(self) -> str: ...


class PageSession(Protocol):
    page: Page
    last_evidence: str

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None: ...

    def snapshot(self, label: str, html: str) -> str: ...


def apply_id(url: str) -> str:
    parsed = urlsplit(url)
    ids = parse_qs(parsed.query).get("jobid", [])
    ctmids = parse_qs(parsed.query).get("ctmid", [])
    check(
        parsed.scheme in {"http", "https"}
        and parsed.hostname == "xyz.51job.com"
        and parsed.path == "/external/apply.aspx"
        and len(ids) == len(ctmids) == 1
        and ids[0].isdigit()
        and ctmids[0].isdigit(),
        "前程无忧公开申请链接缺少岗位 ID 或租户 ID",
    )
    return ids[0]


def split_jobinfo(raw: str) -> tuple[str, str]:
    """Split only visibly headed sections; leave ambiguous prose for review."""
    body = text(raw)
    parts = re.split(r"(岗位职责|工作职责|职位职责|任职要求|岗位要求|任职资格)\s*[：:]?", body)
    duties: list[str] = []
    requirements: list[str] = []
    for label, content in zip(parts[1::2], parts[2::2], strict=True):
        value = content.strip(" \n：:")
        if label in {"岗位职责", "工作职责", "职位职责"}:
            duties.append(value)
        else:
            requirements.append(value)
    return "\n".join(filter(None, duties)), "\n".join(filter(None, requirements))


class Lens(Adapter):
    name = "lens-static"
    host = "campus.51job.com"
    path = "/lens/about1.html"
    scope_description = "蓝思校园招聘页面 obj 全量数组；页面按工作地区切换显示，公开正文无发布日期"

    async def harvest(self) -> None:
        session = cast(PageSession, self.session)
        html = await session.page.content()
        document = BeautifulSoup(html, "html.parser")
        rows = await session.page.evaluate("() => window.obj")
        check(isinstance(rows, list) and bool(rows), "蓝思页面缺少完整岗位数组")
        tabs = [node.get_text(" ", strip=True) for node in document.select(".tab div")]
        check(bool(tabs) and len(tabs) == len(set(tabs)), "蓝思岗位地区选项异常")
        check(
            all(isinstance(row, dict) for row in rows)
            and {str(row.get("attr9", "")) for row in rows} == set(tabs),
            "蓝思岗位数组与页面地区选项不一致",
        )
        rendered = {
            apply_id(str(anchor.get("href", "")))
            for anchor in document.select('.zw a[href*="external/apply.aspx"]')
        }
        check(bool(rendered), "蓝思首个地区没有可核验岗位卡片")
        scope = Scope(name="lens-all-regions", expected=len(rows))
        scope.evidence.append(session.snapshot("lens-directory", html))
        self.result.scopes.append(scope)
        seen: set[str] = set()
        for row in rows:
            scope.listed += 1
            try:
                url = str(row["attr5"])
                job_id = apply_id(url)
                check(job_id not in seen, "蓝思数组存在重复岗位 ID")
                seen.add(job_id)
                scope.unique += 1
                title = text(row["value"])
                duties = text(row.get("岗位职责"))
                requirements = text(row.get("岗位要求"))
                location = text(row.get("attr9"))
                detail = text(row.get("attr2"))
                address_match = re.search(r"工作地点\s*[：:]\s*([^\n]+)", detail)
                address = address_match.group(1).strip() if address_match else ""
                check(bool(title and duties and requirements and location), "蓝思岗位正文缺失")
                job = self.job(
                    job_id,
                    title=title,
                    unit=text(row.get("园区")),
                    category_raw=text(row.get("一级岗位")),
                    location=location,
                    address=address,
                    duties=duties,
                    requirements=requirements,
                    source_url=self.source.url,
                    apply_url=url,
                    field_sources={
                        "title": "window.obj[].value",
                        "duties": "window.obj[].岗位职责",
                        "requirements": "window.obj[].岗位要求",
                        "location": "window.obj[].attr9",
                        "address": "window.obj[].attr2:工作地点"
                        if address
                        else "source_missing:详细地址",
                        "published": "source_missing:无公开发布日期",
                    },
                )
                job.evidence = [session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
            except Exception as exc:
                self.error(exc, str(row.get("value", "")))
        check(rendered.issubset(seen), "蓝思首个地区展示的岗位不在全量数组中")
        scope.terminal = True


class ChinaGas(Adapter):
    name = "chinagas-static"
    host = "campus.51job.com"
    path = "/chinagasholdings/page1.html"
    scope_description = (
        "中国燃气校园招聘页 jobListData 完整数组，按页面 ID 核对；无公开发布日期或截止日"
    )

    async def harvest(self) -> None:
        session = cast(PageSession, self.session)
        entry = BeautifulSoup(await session.page.content(), "html.parser")
        links = [
            anchor
            for anchor in entry.select("a[href]")
            if anchor.get_text(" ", strip=True) == "校园招聘"
        ]
        check(len(links) == 1, "中国燃气入口缺少唯一校园招聘导航")
        target = urljoin(self.source.url, str(links[0].get("href", "")))
        check(
            urlsplit(target).hostname == self.host
            and urlsplit(target).path == "/chinagasholdings/page2.html",
            "中国燃气校园岗位导航目标变化",
        )
        entry_evidence = session.last_evidence
        await session.open(target)
        html = await session.page.content()
        document = BeautifulSoup(html, "html.parser")
        rows = await session.page.evaluate(
            "() => typeof jobListData === 'undefined' ? null : jobListData"
        )
        check(isinstance(rows, list) and bool(rows), "中国燃气页面缺少完整岗位数组")
        cards = document.select(".listbox .list[jobid]")
        check(len(cards) == len(rows), "中国燃气页面卡片数与岗位数组不一致")
        scope = Scope(name="chinagas-campus-all", expected=len(rows))
        scope.evidence.extend([entry_evidence, session.snapshot("chinagas-directory", html)])
        self.result.scopes.append(scope)
        seen: set[str] = set()
        for row, card in zip(rows, cards, strict=True):
            scope.listed += 1
            try:
                check(isinstance(row, dict), "中国燃气岗位数组项结构异常")
                job_id = str(row["jobid"])
                card_id = str(card.get("jobid", ""))
                check(job_id == card_id and job_id.isdigit(), "中国燃气岗位数组与卡片 ID 不一致")
                check(job_id not in seen, "中国燃气岗位 ID 重复")
                seen.add(job_id)
                scope.unique += 1
                ctmid = str(row["ctmid"])
                apply = card.select_one(".list-detail a.apply[href]")
                check(apply is not None, "中国燃气岗位卡片缺少申请链接")
                assert apply is not None
                url = str(apply["href"])
                parsed = urlsplit(url)
                check(
                    apply_id(url) == job_id and parse_qs(parsed.query).get("ctmid") == [ctmid],
                    "中国燃气岗位申请 ID 或租户 ID 不一致",
                )
                title = text(row["jobname"])
                body = text(row["jobinfo"])
                location = text(row["jobarea"])
                check(bool(title and body and location), "中国燃气岗位标题、正文或地点缺失")
                duties, requirements = split_jobinfo(body)
                if not requirements:
                    self.result.warnings.append(
                        Issue(
                            code="field_missing",
                            message="正文无可辨认的任职要求段落，保留待补全",
                            source_id=self.source.source_id,
                            job_key=job_id,
                            url=target,
                        )
                    )
                job = self.job(
                    job_id,
                    title=f"{title} - {location}",
                    location=location,
                    duties=duties,
                    requirements=requirements,
                    source_url=target,
                    apply_url=url,
                    field_sources={
                        "title": "window.jobListData[].jobname/jobarea",
                        "location": "window.jobListData[].jobarea",
                        "duties": "window.jobListData[].jobinfo:岗位职责"
                        if duties
                        else "source_missing:职责段落",
                        "requirements": (
                            "window.jobListData[].jobinfo:任职要求"
                            if requirements
                            else "source_missing:要求段落"
                        ),
                        "published": "source_missing:无公开发布日期",
                    },
                )
                job.evidence = [session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
            except Exception as exc:
                self.error(exc, str(row.get("jobid", "")) if isinstance(row, dict) else "")
        scope.terminal = True


def _pairs(container: Tag) -> list[tuple[Tag, Tag]]:
    children = [child for child in container.children if isinstance(child, Tag)]
    check(bool(children) and len(children) % 2 == 0, "天津银行热招岗位标题与详情数量不一致")
    pairs: list[tuple[Tag, Tag]] = []
    for title, info in zip(children[::2], children[1::2], strict=True):
        title_classes = title.get("class")
        info_classes = info.get("class")
        check(
            isinstance(title_classes, list)
            and "jobtitle" in title_classes
            and isinstance(info_classes, list)
            and "jobinfo" in info_classes,
            "天津银行岗位标题与详情顺序变化",
        )
        pairs.append((title, info))
    return pairs


def _sections(info: Tag) -> dict[str, str]:
    result: dict[str, str] = {}
    for heading in info.select(".jobt"):
        label = heading.get_text(" ", strip=True)
        sibling = heading.find_next_sibling("p")
        sibling_classes = sibling.get("class") if sibling is not None else None
        if sibling is not None and isinstance(sibling_classes, list) and "text2" in sibling_classes:
            result[label] = sibling.get_text("\n", strip=True)
    return result


class TianjinBank(Adapter):
    name = "tjyh-static"
    host = "campus.51job.com"
    path = "/tjyh_2026/contact.html"
    scope_description = "天津银行 2026 热招和经济困难学生专项两个分支；每个城市申请 ID 独立计数"

    async def harvest(self) -> None:
        session = cast(PageSession, self.session)
        entry = BeautifulSoup(await session.page.content(), "html.parser")
        targets: dict[str, str] = {}
        for label, path in (
            ("热招岗位", "/tjyh_2026/job.html"),
            ("专项招聘", "/tjyh_2026/jobs.html"),
        ):
            links = [a for a in entry.select("a[href]") if a.get_text(" ", strip=True) == label]
            check(len(links) == 1, f"天津银行缺少唯一{label}导航")
            target = urljoin(self.source.url, str(links[0].get("href", "")))
            check(
                urlsplit(target).hostname == self.host and urlsplit(target).path == path,
                f"天津银行{label}导航目标变化",
            )
            targets[label] = target
        seen: set[str] = set()
        for label, target in targets.items():
            scope = Scope(name="hot-jobs" if label == "热招岗位" else "special-jobs")
            self.result.scopes.append(scope)
            try:
                await session.open(target)
                document = BeautifulSoup(await session.page.content(), "html.parser")
                evidence = session.snapshot(scope.name, str(document))
                scope.evidence.append(evidence)
                if label == "热招岗位":
                    self._hot(document, target, scope, seen)
                else:
                    self._special(document, target, scope, seen)
                scope.expected = scope.listed
                scope.terminal = True
            except Exception as exc:
                self.error(exc, label)

    def _append(
        self,
        scope: Scope,
        seen: set[str],
        *,
        url: str,
        title: str,
        location: str,
        duties: str,
        requirements: str,
        target: str,
        evidence: str,
    ) -> None:
        scope.listed += 1
        job_id = apply_id(url)
        check(job_id not in seen, "天津银行跨分支或城市重复岗位 ID")
        seen.add(job_id)
        scope.unique += 1
        check(bool(title and location and requirements), "天津银行岗位标题、地区或要求缺失")
        job = self.job(
            job_id,
            title=title,
            location=location,
            duties=duties,
            requirements=requirements,
            source_url=target,
            apply_url=url,
            field_sources={
                "location": "jobcity[data-url]" if location != "天津总部" else ".jobt:工作地点",
                "duties": ".jobinfo .text1" if duties else "source_missing:无独立职责",
                "requirements": ".jobinfo .jobt/.text2 或专项招聘公共条件",
                "published": "source_missing:无公开发布日期",
            },
        )
        job.evidence = [evidence]
        self.result.jobs.append(job)
        scope.details += 1

    def _hot(self, document: BeautifulSoup, target: str, scope: Scope, seen: set[str]) -> None:
        container = document.select_one(".jobContainer")
        check(container is not None, "天津银行热招岗位容器缺失")
        assert container is not None
        for title_node, info in _pairs(container):
            title = title_node.get_text(" ", strip=True)
            duties_node = info.select_one(".text1")
            duties = duties_node.get_text("\n", strip=True) if duties_node else ""
            sections = _sections(info)
            requirements = "\n".join(
                f"{label}\n{sections[label]}"
                for label in ("基本条件", "优先条件", "岗位要求")
                if sections.get(label)
            )
            cities = info.select(".jobcity[data-url]")
            if cities:
                check(len(cities) == len(info.select(".jobcity")), "天津银行热招城市缺少申请 ID")
                for city in cities:
                    self._append(
                        scope,
                        seen,
                        url=str(city["data-url"]),
                        title=title,
                        location=city.get_text(" ", strip=True),
                        duties=duties,
                        requirements=requirements,
                        target=target,
                        evidence=self.session.last_evidence,
                    )
            else:
                apply = info.select_one('a.submit[href*="external/apply.aspx"]')
                check(apply is not None, "天津银行热招岗位缺少申请链接")
                assert apply is not None
                self._append(
                    scope,
                    seen,
                    url=str(apply["href"]),
                    title=title,
                    location=sections.get("工作地点", ""),
                    duties=duties,
                    requirements=requirements,
                    target=target,
                    evidence=self.session.last_evidence,
                )

    def _special(self, document: BeautifulSoup, target: str, scope: Scope, seen: set[str]) -> None:
        title = document.select_one(".jobtips")
        cities = document.select(".content .jobcity[data-url]")
        check(title is not None and bool(cities), "天津银行专项招聘岗位或城市为空")
        check(
            len(cities) == len(document.select(".content .jobcity")), "天津银行专项城市缺少申请 ID"
        )
        assert title is not None
        conditions = [
            node.get_text("\n", strip=True) for node in document.select(".kuang1 .content1 p")
        ]
        tip = document.select_one(".content .tips")
        if tip is not None:
            conditions.append(tip.get_text(" ", strip=True))
        requirements = "\n".join(filter(None, conditions))
        check(bool(requirements), "天津银行专项招聘条件缺失")
        for city in cities:
            self._append(
                scope,
                seen,
                url=str(city["data-url"]),
                title=title.get_text(" ", strip=True),
                location=city.get_text(" ", strip=True),
                duties="",
                requirements=requirements,
                target=target,
                evidence=self.session.last_evidence,
            )


TENANTS = (Lens, ChinaGas, TianjinBank)
